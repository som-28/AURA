(() => {
  const gate = document.getElementById('clerk-auth-gate');
  const authRoot = document.getElementById('clerk-auth-control');
  const userRoot = document.getElementById('clerk-user-control');
  const authError = document.getElementById('auth-error');
  const authCopy = document.getElementById('auth-copy');
  let appStarted = false;

  function showGate(message, error = '') {
    document.documentElement.classList.add('auth-pending');
    gate.hidden = false;
    authCopy.textContent = message;
    authError.hidden = !error;
    authError.textContent = error;
  }

  function loadScript(src, attributes = {}) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.async = true;
      script.crossOrigin = 'anonymous';
      Object.entries(attributes).forEach(([name, value]) => script.setAttribute(name, value));
      script.onload = resolve;
      script.onerror = () => reject(new Error('A required sign-in component could not be loaded.'));
      document.head.appendChild(script);
    });
  }

  function installAuthenticatedFetch() {
    if (window.auraAuthenticatedFetchInstalled) return;
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (input, init = {}) => {
      const inputUrl = input instanceof Request ? input.url : String(input);
      const url = new URL(inputUrl, window.location.href);
      if (url.origin !== window.location.origin) return originalFetch(input, init);
      const headers = new Headers(input instanceof Request ? input.headers : undefined);
      new Headers(init.headers || {}).forEach((value, key) => headers.set(key, value));
      const token = await window.Clerk.session?.getToken();
      if (token) headers.set('Authorization', `Bearer ${token}`);
      return originalFetch(input, { ...init, headers, credentials: init.credentials || 'same-origin' });
    };
    window.auraAuthenticatedFetchInstalled = true;
  }

  async function loadWorkspace() {
    if (appStarted) return;
    appStarted = true;
    gate.hidden = true;
    document.documentElement.classList.remove('auth-pending');
    const loadUserButton = document.getElementById('clerk-user-control');
    if (window.Clerk?.isSignedIn && loadUserButton) {
      loadUserButton.hidden = false;
      window.Clerk.mountUserButton(loadUserButton);
    }
    try {
      await loadScript('/app.js?v=clerk-1');
      await loadScript('/resume-studio.js?v=clerk-1');
    } catch (error) {
      appStarted = false;
      showGate('AURA could not load the workspace.', error.message);
    }
  }

  async function start() {
    try {
      const response = await fetch('/auth/config');
      if (!response.ok) throw new Error('Could not read AURA sign-in settings.');
      const config = await response.json();
      if (!config.required) {
        await loadWorkspace();
        return;
      }
      if (!config.configured || !config.publishable_key) {
        showGate('AURA sign-in is not ready.', 'Add the Clerk development keys to the server environment, then restart AURA.');
        return;
      }

      const encodedDomain = config.publishable_key.split('_')[2];
      const frontendApi = atob(encodedDomain).replace(/\$$/, '');
      if (!frontendApi) throw new Error('The Clerk publishable key is invalid.');
      const base = `https://${frontendApi}`;
      await loadScript(`${base}/npm/@clerk/ui@1/dist/ui.browser.js`);
      await loadScript(`${base}/npm/@clerk/clerk-js@6/dist/clerk.browser.js`, {
        'data-clerk-publishable-key': config.publishable_key,
      });
      const isDark = document.documentElement.classList.contains('dark-mode');
      const authPalette = isDark
        ? { background: '#1c1a20', foreground: '#f0edf4', muted: '#aaa2b2', input: 'transparent', inputText: '#f0edf4', border: '#625b69' }
        : { background: '#f3f0e8', foreground: '#28232e', muted: '#6d6672', input: 'transparent', inputText: '#28232e', border: '#a69daa' };
      await window.Clerk.load({
        ui: { ClerkUI: window.__internal_ClerkUICtor },
        appearance: {
          options: { elevation: 'flush' },
          variables: {
            colorPrimary: '#8a70ae',
            colorBackground: authPalette.background,
            colorForeground: authPalette.foreground,
            colorMutedForeground: authPalette.muted,
            colorInput: authPalette.input,
            colorInputForeground: authPalette.inputText,
            colorBorder: authPalette.border,
            borderRadius: '2px',
            fontFamily: 'Space Grotesk, sans-serif',
          },
          elements: {
            rootBox: { width: '100%', maxWidth: '520px', margin: '0 auto' },
            card: { width: '100%', maxWidth: '520px', margin: '0 auto', padding: '0', border: '0', borderRadius: '0', background: 'transparent', boxShadow: 'none' },
            headerTitle: { display: 'none' },
            headerSubtitle: { display: 'none' },
            formFieldLabel: { fontFamily: 'Space Grotesk, sans-serif', fontSize: '13px', fontWeight: '500', letterSpacing: '0', color: authPalette.foreground },
            formFieldInput: { minHeight: '48px', marginTop: '5px', padding: '11px 12px', borderRadius: '0', border: '0', borderBottom: `1px solid ${authPalette.border}`, backgroundColor: 'transparent', color: authPalette.inputText, boxShadow: 'none', fontFamily: 'Space Grotesk, sans-serif', fontSize: '14px' },
            formButtonPrimary: { minHeight: '46px', borderRadius: '2px', boxShadow: 'none', fontFamily: 'IBM Plex Mono, monospace' },
            socialButtonsBlockButton: { minHeight: '44px', borderRadius: '2px', boxShadow: 'none' },
            footerActionLink: { color: '#8a70ae', fontFamily: 'IBM Plex Mono, monospace' },
          },
        },
      });
      installAuthenticatedFetch();

      if (window.Clerk.isSignedIn) {
        await loadWorkspace();
      } else {
        showGate('Sign in to open your AURA workspace.');
        window.Clerk.mountSignIn(authRoot, {
          withSignUp: true,
          appearance: {
            variables: {
              colorPrimary: '#8a70ae',
              colorBackground: authPalette.background,
              colorForeground: authPalette.foreground,
              colorMutedForeground: authPalette.muted,
              colorInput: authPalette.input,
              colorInputForeground: authPalette.inputText,
              colorBorder: authPalette.border,
              borderRadius: '2px',
              fontFamily: 'Space Grotesk, sans-serif',
            },
            elements: {
              rootBox: { width: '100%', maxWidth: '520px', margin: '0 auto', position: 'relative', left: 'clamp(0px, calc(12.5vw - 100px), 64px)' },
              card: { width: '100%', maxWidth: '520px', margin: '0 auto', padding: '0', border: '0', borderRadius: '0', background: 'transparent', boxShadow: 'none' },
              formFieldLabel: { fontFamily: 'Space Grotesk, sans-serif', fontSize: '13px', fontWeight: '500', letterSpacing: '0', color: authPalette.foreground },
              formFieldInput: { minHeight: '48px', marginTop: '5px', padding: '11px 12px', borderRadius: '0', border: '0', borderBottom: `1px solid ${authPalette.border}`, backgroundColor: 'transparent', color: authPalette.inputText, boxShadow: 'none', fontFamily: 'Space Grotesk, sans-serif', fontSize: '14px' },
            },
          },
        });
      }

      window.Clerk.addListener((state) => {
        if (state.isSignedIn && !appStarted) loadWorkspace();
        else if (state.isLoaded && !state.isSignedIn && appStarted) window.location.reload();
      });
    } catch (error) {
      showGate('AURA could not connect to Clerk.', error?.message || 'Check the server and try again.');
    }
  }

  start();
})();
