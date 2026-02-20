<script>
  import { onMount } from 'svelte';
  import { auth, accounts, currentPage } from './lib/stores.js';
  import api from './lib/api.js';
  import Navigation from './components/Navigation.svelte';
  import Composer from './components/Composer.svelte';
  import Queue from './components/Queue.svelte';
  import Accounts from './components/Accounts.svelte';
  import Login from './components/Login.svelte';
  import Setup from './components/Setup.svelte';

  let error = $state(null);

  onMount(async () => {
    try {
      const status = await api.auth.status();
      auth.set({
        authenticated: status.authenticated,
        user: status.user,
        setupRequired: status.setup_required,
        loading: false,
      });
    } catch (err) {
      auth.set({
        authenticated: false,
        user: null,
        setupRequired: false,
        loading: false,
      });
      error = err.message;
    }
  });

  async function loadAccounts() {
    if (!$auth.authenticated) return;
    
    accounts.update(a => ({ ...a, loading: true, error: null }));
    try {
      const items = await api.accounts.list();
      accounts.set({ items, loading: false, error: null });
    } catch (err) {
      accounts.update(a => ({ ...a, loading: false, error: err.message }));
    }
  }

  $effect(() => {
    if ($auth.authenticated) {
      loadAccounts();
    }
  });

  function handleNavigate(page) {
    currentPage.set(page);
  }

  function handleAuthSuccess() {
    auth.update(a => ({ ...a, authenticated: true, setupRequired: false }));
    loadAccounts();
  }

  function handleLogout() {
    auth.set({
      authenticated: false,
      user: null,
      setupRequired: false,
      loading: false,
    });
    accounts.set({ items: [], loading: false, error: null });
    currentPage.set('composer');
  }
</script>

<main>
  {#if $auth.loading}
    <div class="loading-screen">
      <div class="spinner"></div>
      <p>Loading...</p>
    </div>
  {:else if $auth.setupRequired}
    <Setup on:success={handleAuthSuccess} />
  {:else if !$auth.authenticated}
    <Login on:success={handleAuthSuccess} />
  {:else}
    <Navigation 
      currentPage={$currentPage} 
      user={$auth.user}
      on:navigate={(e) => handleNavigate(e.detail)}
      on:logout={handleLogout}
    />
    <div class="page">
      <div class="container">
        {#if $currentPage === 'composer'}
          <Composer accounts={$accounts.items} />
        {:else if $currentPage === 'queue'}
          <Queue />
        {:else if $currentPage === 'accounts'}
          <Accounts accounts={$accounts.items} on:refresh={loadAccounts} />
        {/if}
      </div>
    </div>
  {/if}
</main>

<style>
  main {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  .loading-screen {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    color: var(--color-text-secondary);
  }

  .loading-screen .spinner {
    width: 2rem;
    height: 2rem;
  }
</style>
