<script>
  import { createEventDispatcher } from 'svelte';
  import api from '../lib/api.js';

  const dispatch = createEventDispatcher();

  let { accounts } = $props();

  let showMastodonForm = $state(false);
  let showBlueskyForm = $state(false);
  let mastodonInstance = $state('');
  let blueskyHandle = $state('');
  let blueskyPassword = $state('');
  let connecting = $state(false);
  let error = $state('');
  let checkingStatus = $state(null);

  async function handleConnectMastodon(e) {
    e.preventDefault();
    error = '';
    connecting = true;

    try {
      const result = await api.accounts.connectMastodon({
        instance_url: mastodonInstance,
      });
      // Redirect to Mastodon OAuth
      window.location.href = result.auth_url;
    } catch (err) {
      error = err.message;
      connecting = false;
    }
  }

  async function handleConnectBluesky(e) {
    e.preventDefault();
    error = '';
    connecting = true;

    try {
      await api.accounts.connectBluesky({
        handle: blueskyHandle,
        app_password: blueskyPassword,
      });
      blueskyHandle = '';
      blueskyPassword = '';
      showBlueskyForm = false;
      dispatch('refresh');
    } catch (err) {
      error = err.message;
    } finally {
      connecting = false;
    }
  }

  async function handleCheckStatus(account) {
    checkingStatus = account.id;
    error = '';
    try {
      await api.accounts.status(account.id);
      dispatch('refresh');
    } catch (err) {
      error = err.message;
    } finally {
      checkingStatus = null;
    }
  }

  async function handleRemove(account) {
    if (!confirm(`Remove ${account.display_name || account.account_id}?`)) {
      return;
    }
    try {
      await api.accounts.remove(account.id);
      dispatch('refresh');
    } catch (err) {
      error = err.message;
    }
  }

  function formatDate(dateString) {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleString();
  }
</script>

<div class="card">
  <div class="card-header">
    <h2 class="card-title">Connected Accounts</h2>
  </div>

  {#if error}
    <div class="alert alert-error">{error}</div>
  {/if}

  {#if accounts.length === 0}
    <div class="empty-state">
      <div class="empty-state-icon">🔗</div>
      <p>No accounts connected</p>
      <p class="text-sm text-muted">Connect your first account below</p>
    </div>
  {:else}
    <div class="accounts-list">
      {#each accounts as account}
        <div class="account-item">
          <div class="account-info">
            <div class="account-avatar">
              {#if account.avatar_url}
                <img src={account.avatar_url} alt="" />
              {:else}
                <div class="account-avatar-placeholder">
                  {account.display_name?.[0] || '?'}
                </div>
              {/if}
            </div>
            <div class="account-details">
              <div class="account-name">
                {account.display_name || account.account_id}
                <span class="badge {account.is_active ? 'badge-published' : 'badge-failed'}">
                  {account.is_active ? 'Active' : 'Inactive'}
                </span>
              </div>
              <div class="account-meta">
                <span class="platform-icon platform-{account.platform}"></span>
                {account.platform}
                {#if account.instance_url}
                  · {account.instance_url}
                {/if}
              </div>
              <div class="account-sync text-xs text-muted">
                Last synced: {formatDate(account.last_synced_at)}
              </div>
            </div>
          </div>
          <div class="btn-group">
            <button
              class="btn btn-sm"
              onclick={() => handleCheckStatus(account)}
              disabled={checkingStatus === account.id}
            >
              {#if checkingStatus === account.id}
                <span class="spinner"></span>
              {:else}
                Check
              {/if}
            </button>
            <button
              class="btn btn-sm btn-error"
              onclick={() => handleRemove(account)}
            >
              Remove
            </button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<!-- Add Account Card -->
<div class="card">
  <h3 class="card-title mb-4">Add Account</h3>

  <div class="btn-group mb-4">
    <button
      class="btn"
      class:btn-primary={showMastodonForm}
      onclick={() => { showMastodonForm = !showMastodonForm; showBlueskyForm = false; }}
    >
      <span class="platform-icon platform-mastodon"></span>
      Mastodon
    </button>
    <button
      class="btn"
      class:btn-primary={showBlueskyForm}
      onclick={() => { showBlueskyForm = !showBlueskyForm; showMastodonForm = false; }}
    >
      <span class="platform-icon platform-bluesky"></span>
      Bluesky
    </button>
  </div>

  {#if showMastodonForm}
    <form onsubmit={handleConnectMastodon}>
      <div class="form-group">
        <label class="form-label" for="instance-url">Instance URL</label>
        <input
          id="instance-url"
          type="text"
          class="form-input"
          bind:value={mastodonInstance}
          placeholder="mastodon.social"
          required
        />
        <p class="form-hint">Enter your Mastodon instance domain</p>
      </div>
      <button type="submit" class="btn btn-primary" disabled={connecting}>
        {#if connecting}
          <span class="spinner"></span>
        {:else}
          Connect Mastodon Account
        {/if}
      </button>
    </form>
  {/if}

  {#if showBlueskyForm}
    <form onsubmit={handleConnectBluesky}>
      <div class="form-group">
        <label class="form-label" for="bluesky-handle">Handle</label>
        <input
          id="bluesky-handle"
          type="text"
          class="form-input"
          bind:value={blueskyHandle}
          placeholder="username.bsky.social"
          required
        />
      </div>
      <div class="form-group">
        <label class="form-label" for="app-password">
          App Password
          <a
            href="https://bsky.app/settings/app-passwords"
            target="_blank"
            rel="noopener noreferrer"
            class="text-xs"
          >
            (Get one here)
          </a>
        </label>
        <input
          id="app-password"
          type="password"
          class="form-input"
          bind:value={blueskyPassword}
          placeholder="xxxx-xxxx-xxxx-xxxx"
          required
        />
        <p class="form-hint">
          App passwords are encrypted and only used to post on your behalf.
          They cannot be used to access your account settings.
        </p>
      </div>
      <button type="submit" class="btn btn-primary" disabled={connecting}>
        {#if connecting}
          <span class="spinner"></span>
        {:else}
          Connect Bluesky Account
        {/if}
      </button>
    </form>
  {/if}
</div>

<style>
  .accounts-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .account-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem;
    background-color: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
  }

  .account-info {
    display: flex;
    align-items: center;
    gap: 0.875rem;
  }

  .account-avatar {
    width: 2.5rem;
    height: 2.5rem;
    border-radius: 50%;
    overflow: hidden;
    flex-shrink: 0;
  }

  .account-avatar img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .account-avatar-placeholder {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: var(--color-primary);
    color: white;
    font-weight: 600;
    font-size: 1rem;
  }

  .account-details {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .account-name {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 500;
  }

  .account-meta {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.875rem;
    color: var(--color-text-secondary);
  }

  .account-sync {
    margin-top: 0.125rem;
  }
</style>
