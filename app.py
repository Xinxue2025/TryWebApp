from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit
import os
import json
import random
from dotenv import load_dotenv
import openai
from PIL import Image
import base64
from io import BytesIO
import time
from threading import Thread

# Load environment variables
load_dotenv()

# Check for OpenAI API Key
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError(
        "OPENAI_API_KEY environment variable is not set. "
        "Please create a .env file in the project root directory "
        "and add your OpenAI API key like this: OPENAI_API_KEY=your_api_key_here"
    )

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
socketio = SocketIO(app)

# Game state
roles_list = ["Villager", "Villager", "Villager", "Hunter", "Seer", "Wolf", "Wolf", "Wolf", "Witch"]
game_state = {
    'roles': [],
    'round': 0,
    'player_status': {},
    'witch_potions': {'healing': 1, 'poison': 1},
    'agents': [],
    'votes': {},
    'night_killed': None,
    'night_saved': None,
    'night_poisoned': None,
    'seer_result': None,
    'banished': None,
    'alive_players': [],
    'day_speaker_index': 0
}

class WerewolfAgent:
    def __init__(self, name, llm_config, roles, role):
        self.name = name
        self.llm_config = llm_config
        self.roles = roles
        self.role = role
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model_name = llm_config.get("model_name", "gpt-3.5-turbo-0125")
        self.client = openai.OpenAI(api_key=self.api_key)

    def say(self, prompt):
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "What do you say?"}
                ],
                temperature=0.8,
                max_tokens=100,
                timeout=10
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating response for {self.name}: {e}")
            return "I'm having trouble thinking right now..."

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('start_game')
def handle_start_game():
    # 初始化游戏状态
    roles = roles_list.copy()
    fixed_roles = [None] * 9
    fixed_roles[5] = "Witch"
    roles.remove("Witch")
    random.shuffle(roles)
    idx = 0
    for i in range(9):
        if fixed_roles[i] is None:
            fixed_roles[i] = roles[idx]
            idx += 1
    llm_config = {
        "model_name": "gpt-3.5-turbo-0125",
        "temperature": 0.8,
        "max_tokens": 100
    }
    game_state['roles'] = fixed_roles
    game_state['round'] = 1
    game_state['player_status'] = {f"Player{i+1}": "alive" for i in range(9)}
    game_state['witch_potions'] = {'healing': 1, 'poison': 1}
    game_state['votes'] = {}
    game_state['night_killed'] = None
    game_state['night_saved'] = None
    game_state['night_poisoned'] = None
    game_state['seer_result'] = None
    game_state['banished'] = None
    agents = []
    for i in range(9):
        try:
            agent = WerewolfAgent(
                name=f"Player{i+1}",
                llm_config=llm_config,
                roles=fixed_roles,
                role=fixed_roles[i]
            )
            agents.append(agent)
        except Exception as e:
            print(f"Failed to initialize Player{i+1}: {e}")
            agents.append(None)
    game_state['agents'] = agents
    emit('game_started', {'roles': fixed_roles})
    emit('host_message', {'message': f"Round {game_state['round']} begins"})
    Thread(target=night_phase).start()

def night_phase():
        socketio.emit('host_message', {'message': "Night falls on the village... Everyone, close your eyes."})
        time.sleep(2)
        socketio.emit('host_message', {'message': "Wolves, open your eyes."})
        time.sleep(2)
        socketio.emit('host_message', {'message': "Wolves, point to your target."})
        time.sleep(2)
        # 狼人杀人（AI自动）
        alive_players = [p for p, status in game_state['player_status'].items() if status == "alive"]
        wolves = [i for i, agent in enumerate(game_state['agents']) if agent and agent.role == "Wolf" and game_state['player_status'][f"Player{i+1}"] == "alive"]
        wolf_targets = [p for p in alive_players if p not in [f"Player{i+1}" for i in wolves]]
        if not wolf_targets:
            return
        killed = random.choice(wolf_targets)
        game_state['night_killed'] = killed
        socketio.emit('host_message', {'message': "Wolves, close your eyes."})
        time.sleep(2)
        socketio.emit('host_message', {'message': "Seer, please open your eyes."})
        time.sleep(2)
        socketio.emit('host_message', {'message': "Seer, check a player (simulated)."})
        time.sleep(2)
        seer_idx = next((i for i, agent in enumerate(game_state['agents']) if agent and agent.role == "Seer" and game_state['player_status'][f"Player{i+1}"] == "alive"), None)
        if seer_idx is not None:
            seer_target = random.choice([p for p in alive_players if p != f"Player{seer_idx+1}"])
            seer_role = game_state['agents'][int(seer_target.replace("Player", ""))-1].role
            game_state['seer_result'] = (seer_target, seer_role)
        else:
            game_state['seer_result'] = None
        socketio.emit('host_message', {'message': "Seer, close your eyes."})
        time.sleep(2)
        socketio.emit('host_message', {'message': "Witch, please open your eyes."})
        time.sleep(2)
        socketio.emit('witch_heal_prompt', {'target': killed})

        
@socketio.on('witch_heal_decision')
def handle_witch_heal_decision(data):
    heal = data.get('heal')
    target = game_state.get('night_killed')
    if heal and game_state['witch_potions']['healing'] > 0:
        game_state['witch_potions']['healing'] -= 1
        game_state['night_saved'] = target
    else:
        game_state['night_saved'] = None
    # 女巫毒人
    alive_players = [p for p, status in game_state['player_status'].items() if status == "alive" and p != "Player6"]
    socketio.emit('witch_poison_prompt', {'alive_players': alive_players})

@socketio.on('witch_poison_decision')
def handle_witch_poison_decision(data):
    poisoned = data.get('poisoned')
    if poisoned and game_state['witch_potions']['poison'] > 0:
        game_state['witch_potions']['poison'] -= 1
        game_state['night_poisoned'] = poisoned
    else:
        game_state['night_poisoned'] = None
    # 下一步：进入白天流程（后续补充）
    Thread(target=run_morning_phase).start()

def run_morning_phase():
    killed = game_state.get('night_killed')
    saved = game_state.get('night_saved')
    poisoned = game_state.get('night_poisoned')
    dead_players = []
    dead_types = {}
    if killed and killed != saved:
        game_state['player_status'][killed] = "dead"
        dead_players.append(killed)
        dead_types[killed] = "killed"
    if poisoned:
        game_state['player_status'][poisoned] = "dead"
        dead_players.append(poisoned)
        dead_types[poisoned] = "poisoned"
    if dead_players:
        socketio.emit('host_message', {'message': f"{', '.join(dead_players)} died last night."})
        socketio.emit('update_dead_avatars', {'dead_info': dead_types})
    else:
        socketio.emit('host_message', {'message': "It was a peaceful night."})
    Thread(target=run_day_speech_phase).start()

def run_day_speech_phase():
    alive_players = [p for p, status in game_state['player_status'].items() if status == "alive"]
    game_state['alive_players'] = alive_players
    game_state['day_speaker_index'] = 0
    socketio.emit('host_message', {'message': "Daytime begins. Alive players will now discuss..."})
    time.sleep(2)
    Thread(target=next_player_speak).start()

def next_player_speak():
    idx = game_state.get('day_speaker_index', 0)
    alive_players = game_state['alive_players']
    if idx < len(alive_players):
        speaker = alive_players[idx]
        if speaker == "Player6":
            socketio.emit('day_speak_prompt', {'player': 'Player6'})
            # 等待前端 player_speak
        else:
            agent = game_state['agents'][int(speaker.replace("Player", "")) - 1]
            alive_players_str = ", ".join(alive_players)
            # 角色定制prompt
            if agent.role == "Wolf":
                prompt = f"You are a werewolf. The alive players are: {alive_players_str}. What do you say to mislead the villagers?"
            elif agent.role == "Seer":
                prompt = f"You are the seer. The alive players are: {alive_players_str}. What do you say to help the village?"
            elif agent.role == "Witch":
                prompt = f"You are the witch. The alive players are: {alive_players_str}. What do you say to help the village?"
            else:
                prompt = f"You are a villager. The alive players are: {alive_players_str}. What do you say to help find the werewolves?"
            msg = agent.say(prompt)
            socketio.emit('player_message', {'player_id': speaker, 'message': msg})
            game_state['day_speaker_index'] = idx + 1
            time.sleep(3)
            Thread(target=next_player_speak).start()
    else:
        Thread(target=run_voting_phase).start()

def run_voting_phase():
    alive_players = [p for p, status in game_state['player_status'].items() if status == "alive"]
    game_state['votes'] = {}
    socketio.emit('voting_prompt', {'alive_players': alive_players})

@socketio.on('player_vote')
def handle_player_vote(data):
    voter = data.get('voter')
    target = data.get('target')
    game_state['votes'][voter] = target
    emit('vote_recorded', {'voter': voter, 'target': target})
    # 检查是否所有人都投票
    alive_players = [p for p, status in game_state['player_status'].items() if status == "alive"]
    if len(game_state['votes']) == len(alive_players):
        Thread(target=finish_voting_phase).start()

def finish_voting_phase():
    from collections import Counter
    vote_counts = Counter(game_state['votes'].values())
    if vote_counts:
        banished, _ = vote_counts.most_common(1)[0]
        game_state['player_status'][banished] = "banished"
        game_state['banished'] = banished
        socketio.emit('host_message', {'message': f"{banished} was banished."})
        socketio.emit('update_dead_avatars', {'dead_info': {banished: "banished"}})
        socketio.emit('final_words_prompt', {'player': banished})
        Thread(target=check_win_condition).start()
    else:
        socketio.emit('host_message', {'message': "No one was banished."})
        Thread(target=next_round).start()

@socketio.on('final_words_done')
def handle_final_words_done(data):
    Thread(target=next_round).start()

def check_win_condition():
    alive_players = [p for p, status in game_state['player_status'].items() if status == "alive"]
    alive_roles = [game_state['agents'][int(p.replace("Player", ""))-1].role for p in alive_players]
    wolf_count = alive_roles.count("Wolf")
    non_wolf_count = len(alive_roles) - wolf_count
    if wolf_count == 0:
        socketio.emit('host_message', {'message': "Villagers win! All wolves are eliminated."})
        socketio.emit('game_over', {'winner': 'Villagers'})
    elif wolf_count >= non_wolf_count:
        socketio.emit('host_message', {'message': "Wolves win! They have overpowered the village."})
        socketio.emit('game_over', {'winner': 'Wolves'})
    else:
        Thread(target=next_round).start()

def next_round():
    game_state['round'] += 1
    socketio.emit('host_message', {'message': f"\n This is round {game_state['round']} "})
    Thread(target=night_phase).start()

@socketio.on('player_speak')
def handle_player_speak(data):
    player_id = data.get('player_id')
    message = data.get('message')
    socketio.emit('player_message', {'player_id': player_id, 'message': message})
    game_state['day_speaker_index'] += 1
    Thread(target=next_player_speak).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
