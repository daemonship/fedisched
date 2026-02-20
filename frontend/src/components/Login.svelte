<script>
  import { createEventDispatcher } from 'svelte';
  import api from '../lib/api.js';

  const dispatch = createEventDispatcher();

  let username = $state('');
  let password = $state('');
  let error = $state('');
  let loading = $state(false);

  async function handleSubmit(e) {
    e.preventDefault();
    error = '';
    loading = true;

    try {
      await api.auth.login({ username, password });
      dispatch('success');
    } catch (err) {
      error = err.message || 'Login failed';
    } finally {
      loading = false;
    }
  }
</script>

<div class="page">
  <div class="container">
    <div class="card" style="max-width: 400px; margin: 2rem auto;">
      <h1 class="text-center mb-4">Log in to Fedisched</h1>

      {#if error}
        <div class="alert alert-error">{error}</div>
      {/if}

      <form onsubmit={handleSubmit}>
        <div class="form-group">
          <label class="form-label" for="username">Username</label>
          <input
            id="username"
            type="text"
            class="form-input"
            bind:value={username}
            placeholder="Enter your username"
            required
            autocomplete="username"
          />
        </div>

        <div class="form-group">
          <label class="form-label" for="password">Password</label>
          <input
            id="password"
            type="password"
            class="form-input"
            bind:value={password}
            placeholder="Enter your password"
            required
            autocomplete="current-password"
          />
        </div>

        <button type="submit" class="btn btn-primary w-full" disabled={loading}>
          {#if loading}
            <span class="spinner"></span>
          {:else}
            Log In
          {/if}
        </button>
      </form>
    </div>
  </div>
</div>
