<script>
  import { countCharacters, MASTODON_LIMIT, BLUESKY_LIMIT } from '../lib/stores.js';
  import api from '../lib/api.js';

  let { accounts } = $props();

  let content = $state('');
  let selectedAccountIds = $state([]);
  let scheduledAt = $state('');
  let submitting = $state(false);
  let error = $state('');
  let success = $state('');

  // Filter active accounts
  let activeAccounts = $derived(accounts.filter(a => a.is_active));

  // Character counts for each platform
  let mastodonCount = $derived(
    activeAccounts.some(a => a.platform === 'mastodon')
      ? countCharacters(content, 'mastodon')
      : null
  );

  let blueskyCount = $derived(
    activeAccounts.some(a => a.platform === 'bluesky')
      ? countCharacters(content, 'bluesky')
      : null
  );

  // Check if any selected account would exceed its limit
  let hasSelectedMastodon = $derived(
    selectedAccountIds.some(id => {
      const acc = accounts.find(a => a.id === id);
      return acc?.platform === 'mastodon';
    })
  );

  let hasSelectedBluesky = $derived(
    selectedAccountIds.some(id => {
      const acc = accounts.find(a => a.id === id);
      return acc?.platform === 'bluesky';
    })
  );

  let canSubmit = $derived(
    content.trim().length > 0 &&
    selectedAccountIds.length > 0 &&
    (!hasSelectedMastodon || (mastodonCount && !mastodonCount.isOverLimit)) &&
    (!hasSelectedBluesky || (blueskyCount && !blueskyCount.isOverLimit))
  );

  function toggleAccount(id) {
    if (selectedAccountIds.includes(id)) {
      selectedAccountIds = selectedAccountIds.filter(aid => aid !== id);
    } else {
      selectedAccountIds = [...selectedAccountIds, id];
    }
  }

  function formatDateTimeLocal(date) {
    const pad = n => n.toString().padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  // Set default scheduled time to 1 hour from now
  function setDefaultSchedule() {
    const now = new Date();
    now.setHours(now.getHours() + 1);
    scheduledAt = formatDateTimeLocal(now);
  }

  async function handlePostNow() {
    await submitPost(null);
  }

  async function handleSchedule() {
    if (!scheduledAt) {
      setDefaultSchedule();
      return;
    }
    await submitPost(new Date(scheduledAt).toISOString());
  }

  async function submitPost(scheduledAtValue) {
    error = '';
    success = '';
    submitting = true;

    try {
      const result = await api.posts.create({
        content: content.trim(),
        account_ids: selectedAccountIds,
        scheduled_at: scheduledAtValue,
      });

      if (scheduledAtValue) {
        success = `Post scheduled for ${new Date(scheduledAtValue).toLocaleString()}`;
      } else {
        const failed = result.results.filter(r => !r.success);
        const succeeded = result.results.filter(r => r.success);

        if (failed.length === 0) {
          success = `Posted successfully to ${succeeded.length} account(s)`;
        } else if (succeeded.length === 0) {
          error = `Failed to post: ${failed[0].error}`;
        } else {
          success = `Posted to ${succeeded.length} account(s), ${failed.length} failed`;
        }
      }

      // Clear form on success
      if (!error) {
        content = '';
        selectedAccountIds = [];
        scheduledAt = '';
      }
    } catch (err) {
      error = err.message;
    } finally {
      submitting = false;
    }
  }
</script>

<div class="card">
  <h2 class="card-title mb-4">Compose Post</h2>

  {#if error}
    <div class="alert alert-error">{error}</div>
  {/if}

  {#if success}
    <div class="alert alert-success">{success}</div>
  {/if}

  <!-- Account Selection -->
  <div class="form-group">
    <span class="form-label">Post to</span>
    {#if activeAccounts.length === 0}
      <p class="text-secondary">
        No connected accounts.
        <button class="btn btn-sm" onclick={() => { /* TODO: navigate to accounts */ }}>Connect an account</button> first.
      </p>
    {:else}
      <div class="checkbox-group">
        {#each activeAccounts as account}
          <label class="checkbox-label" class:checked={selectedAccountIds.includes(account.id)}>
            <input
              type="checkbox"
              checked={selectedAccountIds.includes(account.id)}
              onchange={() => toggleAccount(account.id)}
            />
            <span class="platform-icon platform-{account.platform}"></span>
            <span>{account.display_name || account.account_id}</span>
          </label>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Content -->
  <div class="form-group">
    <label class="form-label" for="content">Content</label>
    <textarea
      id="content"
      class="form-textarea"
      bind:value={content}
      placeholder="What's on your mind?"
      rows="5"
      maxlength="500"
    ></textarea>

    <!-- Character Counters -->
    <div class="char-counter mt-2">
      {#if mastodonCount && hasSelectedMastodon}
        <span class="char-counter-item" class:warning={mastodonCount.remaining < 50} class:error={mastodonCount.isOverLimit}>
          <span class="platform-icon platform-mastodon"></span>
          Mastodon: {mastodonCount.remaining}
        </span>
      {/if}
      {#if blueskyCount && hasSelectedBluesky}
        <span class="char-counter-item" class:warning={blueskyCount.remaining < 50} class:error={blueskyCount.isOverLimit}>
          <span class="platform-icon platform-bluesky"></span>
          Bluesky: {blueskyCount.remaining}
        </span>
      {/if}
      {#if !hasSelectedMastodon && !hasSelectedBluesky}
        <span class="text-muted">Select accounts to see character limits</span>
      {/if}
    </div>

    {#if mastodonCount?.isOverLimit && hasSelectedMastodon}
      <p class="form-error">Exceeds Mastodon's {MASTODON_LIMIT} character limit</p>
    {/if}
    {#if blueskyCount?.isOverLimit && hasSelectedBluesky}
      <p class="form-error">Exceeds Bluesky's {BLUESKY_LIMIT} character limit</p>
    {/if}
  </div>

  <!-- Schedule DateTime -->
  <div class="form-group">
    <label class="form-label" for="scheduled-at">Schedule for (optional)</label>
    <input
      id="scheduled-at"
      type="datetime-local"
      class="form-input"
      bind:value={scheduledAt}
    />
    <p class="form-hint">Leave empty to post immediately</p>
  </div>

  <!-- Actions -->
  <div class="btn-group">
    <button
      class="btn btn-primary"
      onclick={handlePostNow}
      disabled={!canSubmit || submitting}
    >
      {#if submitting && !scheduledAt}
        <span class="spinner"></span>
      {:else}
        Post Now
      {/if}
    </button>
    <button
      class="btn"
      onclick={handleSchedule}
      disabled={!canSubmit || submitting || !scheduledAt}
    >
      {#if submitting && scheduledAt}
        <span class="spinner"></span>
      {:else}
        Schedule
      {/if}
    </button>
  </div>
</div>
