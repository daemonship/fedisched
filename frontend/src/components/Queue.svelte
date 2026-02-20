<script>
  import { onMount } from 'svelte';
  import { posts } from '../lib/stores.js';
  import api from '../lib/api.js';

  let activeTab = $state('all');
  let loading = $state(false);
  let error = $state('');
  let retryingId = $state(null);
  let deletingId = $state(null);

  const tabs = [
    { id: 'all', label: 'All' },
    { id: 'scheduled', label: 'Scheduled' },
    { id: 'published', label: 'Published' },
    { id: 'failed', label: 'Failed' },
  ];

  async function loadPosts() {
    loading = true;
    error = '';
    try {
      const params = {};
      if (activeTab !== 'all') {
        params.status = activeTab;
      }
      const items = await api.posts.list(params);
      posts.set({ items, loading: false, error: null });
    } catch (err) {
      error = err.message;
      posts.update(p => ({ ...p, error: err.message }));
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    loadPosts();
  });

  function setTab(tab) {
    activeTab = tab;
    loadPosts();
  }

  async function handleRetry(postId) {
    retryingId = postId;
    error = '';
    try {
      await api.posts.retry(postId);
      await loadPosts();
    } catch (err) {
      error = err.message;
    } finally {
      retryingId = null;
    }
  }

  async function handleDelete(postId) {
    if (!confirm('Are you sure you want to delete this post?')) {
      return;
    }
    deletingId = postId;
    error = '';
    try {
      await api.posts.remove(postId);
      await loadPosts();
    } catch (err) {
      error = err.message;
    } finally {
      deletingId = null;
    }
  }

  function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString();
  }

  function getStatusBadgeClass(status) {
    switch (status) {
      case 'scheduled': return 'badge-scheduled';
      case 'published': return 'badge-published';
      case 'failed': return 'badge-failed';
      case 'publishing': return 'badge-publishing';
      default: return '';
    }
  }

  function truncateContent(content, maxLength = 150) {
    if (content.length <= maxLength) return content;
    return content.slice(0, maxLength) + '...';
  }
</script>

<div class="card">
  <div class="card-header">
    <h2 class="card-title">Post Queue</h2>
    <button class="btn btn-sm" onclick={loadPosts} disabled={loading}>
      {#if loading}
        <span class="spinner"></span>
      {:else}
        Refresh
      {/if}
    </button>
  </div>

  {#if error}
    <div class="alert alert-error">{error}</div>
  {/if}

  <div class="tabs">
    {#each tabs as tab}
      <button
        class="tab"
        class:active={activeTab === tab.id}
        onclick={() => setTab(tab.id)}
      >
        {tab.label}
      </button>
    {/each}
  </div>

  {#if $posts.items.length === 0}
    <div class="empty-state">
      <div class="empty-state-icon">📭</div>
      <p>No posts found</p>
      {#if activeTab === 'scheduled'}
        <p class="text-sm text-muted">Scheduled posts will appear here</p>
      {:else if activeTab === 'published'}
        <p class="text-sm text-muted">Published posts will appear here</p>
      {:else if activeTab === 'failed'}
        <p class="text-sm text-muted">Failed posts will appear here</p>
      {:else}
        <p class="text-sm text-muted">Create your first post to get started</p>
      {/if}
    </div>
  {:else}
    <div class="posts-list">
      {#each $posts.items as post}
        <div class="post-item">
          <div class="post-header">
            <div class="post-meta">
              <span class="badge {getStatusBadgeClass(post.status)}">
                {post.status}
              </span>
              <span class="post-platform">
                <span class="platform-icon platform-{post.platform}"></span>
                {post.account_display_name || post.platform}
              </span>
            </div>
            <span class="post-time">
              {#if post.status === 'published'}
                {formatDate(post.published_at)}
              {:else}
                {formatDate(post.scheduled_at)}
              {/if}
            </span>
          </div>

          <div class="post-content">{truncateContent(post.content)}</div>

          {#if post.last_error}
            <div class="post-error">
              Error: {post.last_error}
            </div>
          {/if}

          <div class="post-footer">
            <span class="text-xs text-muted">
              {post.retry_count > 0 ? `${post.retry_count} retry attempts` : 'No retries'}
            </span>
            <div class="btn-group">
              {#if post.status === 'failed'}
                <button
                  class="btn btn-sm"
                  onclick={() => handleRetry(post.id)}
                  disabled={retryingId === post.id}
                >
                  {#if retryingId === post.id}
                    <span class="spinner"></span>
                  {:else}
                    Retry
                  {/if}
                </button>
              {/if}
              
              {#if post.status !== 'published'}
                <button
                  class="btn btn-sm btn-error"
                  onclick={() => handleDelete(post.id)}
                  disabled={deletingId === post.id}
                >
                  {#if deletingId === post.id}
                    <span class="spinner"></span>
                  {:else}
                    Delete
                  {/if}
                </button>
              {/if}
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
