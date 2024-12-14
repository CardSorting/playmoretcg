function ensureEffectScriptLoaded(callback) {
    if (typeof MTGCard3DTiltEffect === 'undefined') {
        console.log('Loading card effects script...');
        const script = document.createElement('script');
        script.src = '/static/js/card-effects.js';
        script.onload = function() {
            console.log('Card effects script loaded successfully');
            if (callback) callback();
        };
        script.onerror = function() {
            console.error('Failed to load card effects script');
        };
        document.head.appendChild(script);
    } else {
        if (callback) callback();
    }
}

function initializeCard(img) {
    const rarity = img.getAttribute('data-rarity');
    switch (rarity) {
        case 'Mythic Rare':
            img.classList.add('rarity-mythic');
            break;
        case 'Rare':
            img.classList.add('rarity-rare');
            break;
        case 'Uncommon':
            img.classList.add('rarity-uncommon');
            break;
    }
}

function initializeCardEffects() {
    ensureEffectScriptLoaded(function() {
        document.querySelectorAll('.card-back').forEach(function(cardBack) {
            const cardImage = cardBack.querySelector('.card-image');
            if (cardImage) {
                const rarity = cardImage.getAttribute('data-rarity');
                if (rarity === 'Rare' || rarity === 'Mythic Rare') {
                    console.log('Initializing 3D effect for', rarity, 'card');
                    new MTGCard3DTiltEffect(cardBack);
                }
            }
        });
    });
}

function flipCard(index) {
    const card = document.getElementById('card-' + index);
    if (!card.classList.contains('flipped')) {
        card.classList.add('flipped');
        // Initialize 3D effect after flip
        setTimeout(function() {
            const cardBack = card.querySelector('.card-back');
            const cardImage = cardBack.querySelector('.card-image');
            if (cardImage) {
                const rarity = cardImage.getAttribute('data-rarity');
                if (rarity === 'Rare' || rarity === 'Mythic Rare') {
                    initializeCardEffects();
                }
            }
        }, 600); // Wait for flip animation to complete
    }
}

function flipAllCards() {
    const cards = document.querySelectorAll('.card');
    cards.forEach(function(card, index) {
        setTimeout(function() {
            if (!card.classList.contains('flipped')) {
                card.classList.add('flipped');
            }
        }, index * 200); // Stagger the flips
    });

    // Initialize 3D effects after all cards are flipped
    setTimeout(function() {
        initializeCardEffects();
    }, cards.length * 200 + 600);
}

// Auto-reveal cards one by one after a short delay
document.addEventListener('DOMContentLoaded', function() {
    // Initialize card rarity effects
    document.querySelectorAll('.card-image').forEach(initializeCard);
    
    // Setup reveal animations
    const cardWrappers = document.querySelectorAll('.card-wrapper');
    cardWrappers.forEach(function(wrapper, index) {
        wrapper.style.opacity = '0';
        setTimeout(function() {
            wrapper.classList.add('reveal-animation');
        }, index * 200); // Stagger the reveals
    });
    
    // Start flipping cards after all are revealed
    setTimeout(flipAllCards, cardWrappers.length * 200 + 500);
});