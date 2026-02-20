<script>
  import { createEventDispatcher } from 'svelte';
  import api from '../lib/api.js';

  const dispatch = createEventDispatcher();

  let username = $state('');
  let password = $state('');
  let confirmPassword = $state('');
  let email = $state('');
  let error = $state('');
  let loading = $state(false);

  async function handleSubmit(e) {
    e.preventDefault();
    error = '';

    if (password !== confirmPassword) {
      error = 'Passwords do not match';
      return;
    }

    if (password.length < 8) {
      error = 'Password must be at least 8 characters';
      return;
    }

    loading = true;
    try {
      await api.auth.setup({ username, password, email: email || undefined });
      dispatch('success');
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }
</script>

<div class="page">
  <div class="container">
    <div class="card" style="max-width: 400px; margin: 2rem auto;">
      <h1 class="text-center mb-4">Welcome to Fedisched</h1>
      <p class="text-center text-secondary mb-4">
        Create your admin account to get started.
      </p>

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
            placeholder="Choose a username"
            required
            minlength="3"
            maxlength="50"
          />
        </div>

        <div class="form-group">
          <label class="form-label" for="email">Email (optional)</label>
          <input
            id="email"
            type="email"
            class="form-input"
            bind:value={email}
            placeholder="you@example.com"
          />
        </div>

        <div class="form-group">
          <label class="form-label" for="password">Password</label>
          <input
            id="password"
            type="password"
            class="form-input"
            bind:value={password}
            placeholder="Create a password"
            required
            minlength="8"
          />
          <p class="form-hint">At least 8 characters</p>
        </div>

        <div class="form-group">
          <label class="form-label" for="confirm-password">Confirm Password</label>
          <input
            id="confirm-password"
            type="password"
            class="form-input"
            bind:value={confirmPassword}
            placeholder="Confirm your password"
            required
          />
        </div>

        <button type="submit" class="btn btn-primary w-full" disabled={loading}>
          {#if loading}
            <span class="spinner"></span>
          {:else}
            Create Account
          {/if}
        </button>
      </form>
    </div>
  </div>
</div>
