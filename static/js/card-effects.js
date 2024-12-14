class MTGCard3DTiltEffect {
    constructor(cardElement, isLightbox = false) {
        console.log('Initializing MTGCard3DTiltEffect', isLightbox ? 'for lightbox' : 'for card');
        this.card = cardElement;
        this.isLightbox = isLightbox;
        if (!this.card) throw new Error('No card element provided');

        // Find existing elements or create new ones
        this.shine = this.card.querySelector('.shine-effect') || this.createShineElement();
        this.rainbowShine = this.card.querySelector('.rainbow-shine-effect') || this.createRainbowShineElement();

        this.settings = {
            tiltEffectMaxRotation: isLightbox ? 20 : 15,
            tiltEffectPerspective: isLightbox ? 1000 : 800,
            tiltEffectScale: isLightbox ? 1.05 : 1.03,
            shineMovementRange: isLightbox ? 150 : 100,
            rainbowShineMovementRange: isLightbox ? 75 : 50
        };

        this.isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
        this.gyroAvailable = false;

        this.init();
        console.log('Effect initialized with settings:', this.settings);
    }

    init() {
        if (this.isMobile && this.isLightbox) {
            this.setupGyro();
        }
        this.setupEventListeners();
        this.setupInitialState();
    }

    setupInitialState() {
        requestAnimationFrame(() => {
            this.card.style.transform = `
                perspective(${this.settings.tiltEffectPerspective}px)
                rotateX(0deg)
                rotateY(0deg)
                scale3d(1, 1, 1)
            `;
            this.card.style.transformStyle = 'preserve-3d';
            this.card.style.willChange = 'transform';
        });
    }

    createShineElement() {
        const shine = this.createAndAppendElement('shine-effect');
        shine.style.cssText = `
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            pointer-events: none;
            opacity: 0;
            z-index: 2;
            mix-blend-mode: soft-light;
            background: radial-gradient(
                circle at 50% 50%,
                rgba(255, 255, 255, 0.8) 0%,
                rgba(255, 255, 255, 0.5) 25%,
                rgba(255, 255, 255, 0.3) 50%,
                rgba(255, 255, 255, 0.1) 75%,
                rgba(255, 255, 255, 0) 100%
            );
        `;
        return shine;
    }

    createRainbowShineElement() {
        const container = this.createAndAppendElement('rainbow-shine-container');
        container.style.cssText = `
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            pointer-events: none;
            z-index: 1;
        `;
        
        const effect = this.createAndAppendElement('rainbow-shine-effect');
        effect.style.cssText = `
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            opacity: 0;
            mix-blend-mode: color-dodge;
            filter: blur(10px);
            background: radial-gradient(
                circle at 50% 50%,
                rgba(255, 0, 0, 0.3),
                rgba(255, 165, 0, 0.3),
                rgba(255, 255, 0, 0.3),
                rgba(0, 255, 0, 0.3),
                rgba(0, 0, 255, 0.3),
                rgba(75, 0, 130, 0.3),
                rgba(238, 130, 238, 0.3)
            );
        `;
        container.appendChild(effect);
        return effect;
    }

    createAndAppendElement(className) {
        const element = document.createElement('div');
        element.classList.add(className);
        this.card.appendChild(element);
        return element;
    }

    setupEventListeners() {
        if (!this.isMobile || !this.isLightbox) {
            console.log('Setting up mouse events');
            this.card.addEventListener('mouseenter', () => {
                console.log('Mouse enter');
                this.setTransition(false);
            });
            this.card.addEventListener('mousemove', (e) => this.handleTilt(e));
            this.card.addEventListener('mouseleave', () => {
                console.log('Mouse leave');
                this.resetTilt();
            });
        }
    }

    setupGyro() {
        console.log('Setting up gyroscope');
        if (typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function') {
            DeviceOrientationEvent.requestPermission()
                .then(response => {
                    if (response === 'granted') {
                        this.gyroAvailable = true;
                        window.addEventListener('deviceorientation', this.handleGyro.bind(this));
                        console.log('Gyroscope permission granted');
                    }
                })
                .catch(console.error);
        } else if (typeof DeviceOrientationEvent !== 'undefined') {
            this.gyroAvailable = true;
            window.addEventListener('deviceorientation', this.handleGyro.bind(this));
            console.log('Gyroscope available');
        }
    }

    handleTilt(e) {
        const rect = this.card.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const mouseX = e.clientX - centerX;
        const mouseY = e.clientY - centerY;
        
        const angleX = (mouseY / (rect.height / 2)) * this.settings.tiltEffectMaxRotation;
        const angleY = (-mouseX / (rect.width / 2)) * this.settings.tiltEffectMaxRotation;

        this.updateTransform(angleX, angleY);
    }

    handleGyro(event) {
        if (!this.gyroAvailable) return;

        const { beta, gamma } = event;
        if (beta === null || gamma === null) return;

        const clampedBeta = Math.max(-90, Math.min(beta, 90));
        const clampedGamma = Math.max(-45, Math.min(gamma, 45));

        const angleX = (clampedBeta / 90) * this.settings.tiltEffectMaxRotation;
        const angleY = (clampedGamma / 45) * this.settings.tiltEffectMaxRotation;

        this.updateTransform(angleX, angleY);
    }

    updateTransform(angleX, angleY) {
        requestAnimationFrame(() => {
            this.card.style.transform = `
                perspective(${this.settings.tiltEffectPerspective}px)
                rotateX(${angleX}deg)
                rotateY(${angleY}deg)
                scale3d(${this.settings.tiltEffectScale}, ${this.settings.tiltEffectScale}, ${this.settings.tiltEffectScale})
            `;

            const angleXNormalized = angleX / this.settings.tiltEffectMaxRotation;
            const angleYNormalized = angleY / this.settings.tiltEffectMaxRotation;

            this.updateShineEffect(this.shine, angleXNormalized, angleYNormalized, this.settings.shineMovementRange);
            this.updateShineEffect(this.rainbowShine, angleXNormalized, angleYNormalized, this.settings.rainbowShineMovementRange);
        });
    }

    updateShineEffect(element, angleX, angleY, range) {
        const x = -angleY * range;
        const y = -angleX * range;
        element.style.transform = `translate(${x}%, ${y}%)`;
        element.style.opacity = '1';
    }

    setTransition(active) {
        const transition = active ? 'all 0.5s ease-out' : 'none';
        this.card.style.transition = transition;
        this.shine.style.transition = transition;
        this.rainbowShine.style.transition = transition;
    }

    resetTilt() {
        this.setTransition(true);
        requestAnimationFrame(() => {
            this.card.style.transform = `
                perspective(${this.settings.tiltEffectPerspective}px)
                rotateX(0deg)
                rotateY(0deg)
                scale3d(1, 1, 1)
            `;
            this.resetShineEffect(this.shine);
            this.resetShineEffect(this.rainbowShine);
        });
    }

    resetShineEffect(element) {
        element.style.transform = 'translate(0%, 0%)';
        element.style.opacity = '0';
    }

    destroy() {
        if (this.gyroAvailable) {
            window.removeEventListener('deviceorientation', this.handleGyro.bind(this));
        }
        this.card.removeEventListener('mouseenter', () => this.setTransition(false));
        this.card.removeEventListener('mousemove', (e) => this.handleTilt(e));
        this.card.removeEventListener('mouseleave', () => this.resetTilt());
    }
}