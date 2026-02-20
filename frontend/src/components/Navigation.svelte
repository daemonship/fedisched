<script>
  import { createEventDispatcher } from 'svelte';
  import api from '../lib/api.js';

  const dispatch = createEventDispatcher();

  let { currentPage, user } = $props();

  async function handleLogout() {
    try {
      await api.auth.logout();
      dispatch('logout');
    } catch (err) {
      console.error('Logout failed:', err);
    }
  }

  function navigate(page) {
    dispatch('navigate', page);
  }
</script>

<nav class="nav">
  <div class="container nav-content">
    <a href="/" class="nav-brand" onclick={(e) => { e.preventDefault(); navigate('composer'); }}>
      Fedisched
    </a>
    <div class="nav-links">
      <button 
        class="nav-link" 
        class:active={currentPage === 'composer'}
        onclick={() => navigate('composer')}
      >
        Compose
      </button>
      <button 
        class="nav-link" 
        class:active={currentPage === 'queue'}
        onclick={() => navigate('queue')}
      >
        Queue
      </button>
      <button 
        class="nav-link" 
        class:active={currentPage === 'accounts'}
        onclick={() => navigate('accounts')}
      >
        Accounts
      </button>
      <button class="nav-link" onclick={handleLogout}>
        Logout ({user?.username})
      </button>
    </div>
  </div>
</nav>
