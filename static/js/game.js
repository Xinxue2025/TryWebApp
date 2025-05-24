// Initialize Socket.IO connection
const socket = io();

// Game state
let gameState = {
    isGameStarted: false,
    isWitchTurn: false,
    isVotingPhase: false,
    isHealingPhase: false,
    isPoisoningPhase: false,
    coins: 1,
    healingPotion: 1,
    poisonPotion: 1,
    playerStatus: {},
    currentPhase: null,
    witchTarget: null
};

// DOM Elements
const startGameBtn = document.getElementById('startGame');
const quitGameBtn = document.getElementById('quitGame');
const messageInput = document.getElementById('messageInput');
const submitMessageBtn = document.getElementById('submitMessage');
const aiReplyBtn = document.getElementById('aiReply');
const logContainer = document.querySelector('.log-container');
const avatarContainer = document.querySelector('.avatar-container');
const witchControls = document.querySelector('.witch-controls');
const coinCount = document.getElementById('coinCount');
const healingPotionCount = document.getElementById('healingPotion');
const poisonPotionCount = document.getElementById('poisonPotion');

// Initialize player avatars
function initializeAvatars() {
    avatarContainer.innerHTML = "";
    for (let i = 1; i <= 9; i++) {
        const avatar = document.createElement('img');
        avatar.src = `/static/images/Player${i}.png`;
        avatar.alt = `Player ${i}`;
        avatar.className = 'player-avatar';
        avatar.dataset.playerId = i;
        avatar.addEventListener('click', handleAvatarClick);
        avatarContainer.appendChild(avatar);
    }
}

// Add message to log
function addMessage(message, type = 'host') {
    const messageElement = document.createElement('div');
    messageElement.className = `message ${type}-message`;
    messageElement.textContent = message;
    logContainer.appendChild(messageElement);
    logContainer.scrollTop = logContainer.scrollHeight;
}

// Handle avatar click
function handleAvatarClick(event) {
    const playerId = event.target.dataset.playerId;
    if (gameState.isWitchTurn) {
        if (gameState.isHealingPhase) {
            socket.emit('witch_heal_decision', { heal: true });
            gameState.isHealingPhase = false;
            gameState.isWitchTurn = false;
            hideWitchControls();
        } else if (gameState.isPoisoningPhase) {
            socket.emit('witch_poison_decision', { poisoned: `Player${playerId}` });
            gameState.isPoisoningPhase = false;
            gameState.isWitchTurn = false;
            hideWitchControls();
        }
    } else if (gameState.isVotingPhase) {
        socket.emit('player_vote', { voter: 'Player6', target: `Player${playerId}` });
    }
}

// Socket event handlers
socket.on('connect', () => {
    console.log('Connected to server');
});

socket.on('game_started', (data) => {
    gameState.isGameStarted = true;
    gameState.playerStatus = data.roles;
    addMessage('Game started!');
    initializeAvatars();
});

socket.on('host_message', (data) => {
    addMessage(data.message, 'host');
});

socket.on('player_message', (data) => {
    addMessage(`${data.player_id}: ${data.message}`, 'player');
});

socket.on('witch_action_result', (data) => {
    if (data.type === 'heal') {
        gameState.healingPotion--;
        healingPotionCount.textContent = `Healing: ${gameState.healingPotion}`;
    } else if (data.type === 'poison') {
        gameState.poisonPotion--;
        poisonPotionCount.textContent = `Poison: ${gameState.poisonPotion}`;
    }
});

socket.on('vote_recorded', (data) => {
    addMessage(`${data.voter} voted for ${data.target}`);
});

// Add handler for dead avatar updates
socket.on('update_dead_avatars', (data) => {
    const deadInfo = data.dead_info;
    for (const [playerId, deathType] of Object.entries(deadInfo)) {
        const playerNum = playerId.replace('Player', '');
        const avatar = document.querySelector(`.player-avatar[data-player-id="${playerNum}"]`);
        if (avatar) {
            avatar.src = `/static/images/${playerId}_${deathType}.png`;
            avatar.classList.add('dead');
        }
    }
});

socket.on('witch_heal_prompt', (data) => {
    showWitchControls('heal', data.target);
    addMessage(`Wolves want to kill ${data.target}. Do you want to use healing potion?`, 'host');
});

socket.on('witch_poison_prompt', (data) => {
    showWitchControls('poison', null);
    addMessage('Do you want to use poison tonight?', 'host');
});

socket.on('day_speak_prompt', (data) => {
    if (data.player === 'Player6') {
        addMessage('Your Turn to Speak', 'host');
        messageInput.disabled = false;
        submitMessageBtn.disabled = false;
        aiReplyBtn.disabled = false;
    } else {
        addMessage(`Turn to ${data.player} Speak...`, 'host');
        messageInput.disabled = true;
        submitMessageBtn.disabled = true;
        aiReplyBtn.disabled = true;
    }
});

socket.on('ai_reply_result', (data) => {
    messageInput.value = data.message;
});

// Button event handlers
startGameBtn.addEventListener('click', () => {
    socket.emit('start_game');
});

quitGameBtn.addEventListener('click', () => {
    window.location.reload();
});

submitMessageBtn.addEventListener('click', () => {
    const message = messageInput.value.trim();
    if (message) {
        socket.emit('player_speak', {
            player_id: 'Player6',
            message: message
        });
        messageInput.value = '';
    }
});

aiReplyBtn.addEventListener('click', () => {
    if (gameState.coins > 0) {
        gameState.coins--;
        coinCount.textContent = `Coins: ${gameState.coins}`;
        socket.emit('ai_reply_request');
    } else {
        addMessage('Not enough coins for AI reply!', 'host');
    }
});

// Witch control buttons
document.getElementById('healButton').onclick = function() {
    socket.emit('witch_heal_decision', { heal: true });
    hideWitchControls();
};
document.getElementById('notHealButton').onclick = function() {
    socket.emit('witch_heal_decision', { heal: false });
    hideWitchControls();
};
document.getElementById('poisonButton').onclick = function() {
    addMessage('Please click a player to poison.', 'host');
    gameState.isPoisoningPhase = true;
    gameState.isWitchTurn = true;
};
document.getElementById('notPoisonButton').onclick = function() {
    socket.emit('witch_poison_decision', { poisoned: null });
    hideWitchControls();
};

function showWitchControls(type, target) {
    witchControls.style.display = 'block';
    gameState.isWitchTurn = true;
    gameState.witchTarget = target;
    gameState.witchActionType = type;
    
    if (type === 'heal') {
        gameState.isHealingPhase = true;
        gameState.isPoisoningPhase = false;
    } else if (type === 'poison') {
        gameState.isHealingPhase = false;
        gameState.isPoisoningPhase = true;
    }
}

function hideWitchControls() {
    witchControls.style.display = 'none';
    gameState.isWitchTurn = false;
    gameState.isHealingPhase = false;
    gameState.isPoisoningPhase = false;
    gameState.witchTarget = null;
    gameState.witchActionType = null;
}

// Initialize the game
initializeAvatars();
