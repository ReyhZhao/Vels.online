import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Pencil, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import api from '../lib/axios';

function formatDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('en-AU', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function AdminPostList() {
  const [posts, setPosts] = useState([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selected, setSelected] = useState(new Set());
  const [sortKey, setSortKey] = useState('');
  const [sortOrder, setSortOrder] = useState('asc');

  function setSort(key) {
    if (sortKey === key) {
      setSortOrder(o => (o === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortOrder('asc');
    }
  }

  const loadPosts = () => {
    api.get('/api/posts/').then((res) => { setPosts(res.data); setSelected(new Set()); });
  };

  useEffect(() => {
    loadPosts();
  }, []);

  const handleDelete = async (slug) => {
    if (!window.confirm('Delete this post?')) return;
    await api.delete(`/api/posts/${slug}/`);
    loadPosts();
  };

  const filtered = posts.filter(p => {
    const matchStatus = !statusFilter || p.status === statusFilter;
    const q = search.toLowerCase();
    const matchSearch = !q || (p.title || '').toLowerCase().includes(q);
    return matchStatus && matchSearch;
  });

  const sorted = sortKey
    ? [...filtered].sort((a, b) => {
        const dir = sortOrder === 'asc' ? 1 : -1;
        if (sortKey === 'published_at') {
          const av = a.published_at ? new Date(a.published_at).getTime() : 0;
          const bv = b.published_at ? new Date(b.published_at).getTime() : 0;
          return (av - bv) * dir;
        }
        return (a[sortKey] || '').toString().toLowerCase().localeCompare((b[sortKey] || '').toString().toLowerCase()) * dir;
      })
    : filtered;

  const allSelected = sorted.length > 0 && sorted.every(p => selected.has(p.slug));

  function toggleSelect(slug) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  }

  function toggleSelectAll() {
    setSelected(allSelected ? new Set() : new Set(sorted.map(p => p.slug)));
  }

  async function handleBulkDelete() {
    const slugs = [...selected];
    if (!window.confirm(`Delete ${slugs.length} post${slugs.length !== 1 ? 's' : ''}? This cannot be undone.`)) return;
    for (const slug of slugs) {
      try { await api.delete(`/api/posts/${slug}/`); } catch { /* continue */ }
    }
    loadPosts();
  }

  async function handleBulkSetStatus(status) {
    const slugs = [...selected];
    for (const slug of slugs) {
      try { await api.patch(`/api/posts/${slug}/`, { status }); } catch { /* continue */ }
    }
    loadPosts();
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Posts</h1>
          <p className="text-sm text-muted-foreground">Manage your blog posts</p>
        </div>
        <Button asChild size="sm">
          <Link to="/admin/posts/new">New Post</Link>
        </Button>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="search"
          placeholder="Search posts…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          aria-label="Search posts"
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-52"
        />
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          aria-label="Status filter"
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All statuses</option>
          <option value="published">Published</option>
          <option value="draft">Draft</option>
        </select>
      </div>

      {/* Mobile card list */}
      <div className="sm:hidden space-y-2">
        {sorted.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {posts.length === 0 ? 'No posts yet. Create your first post.' : 'No posts match your filters.'}
          </p>
        ) : sorted.map(post => (
          <div key={post.slug} className="rounded-lg border border-border bg-card px-4 py-3 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={selected.has(post.slug)}
                  onChange={() => toggleSelect(post.slug)}
                  className="mt-1 h-4 w-4 rounded border-border text-primary focus:ring-primary"
                  aria-label={`Select ${post.title}`}
                />
                <p className="font-medium text-foreground leading-snug">{post.title}</p>
              </div>
              <Badge variant={post.status === 'published' ? 'default' : 'secondary'} className="shrink-0">
                {post.status}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">{formatDate(post.published_at)}</p>
            <div className="flex gap-2">
              <Button asChild variant="ghost" size="sm">
                <Link to={`/admin/posts/${post.slug}/edit`}>
                  <Pencil className="mr-1 h-3.5 w-3.5" />
                  Edit
                </Link>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={() => handleDelete(post.slug)}
              >
                <Trash2 className="mr-1 h-3.5 w-3.5" />
                Delete
              </Button>
            </div>
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleSelectAll}
                  className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                  aria-label="Select all"
                />
              </TableHead>
              <TableHead>
                <button onClick={() => setSort('title')} className="flex items-center gap-1 hover:text-foreground transition-colors" aria-label="Sort by Title">
                  Title{sortKey === 'title' && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
                </button>
              </TableHead>
              <TableHead>
                <button onClick={() => setSort('status')} className="flex items-center gap-1 hover:text-foreground transition-colors" aria-label="Sort by Status">
                  Status{sortKey === 'status' && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
                </button>
              </TableHead>
              <TableHead>
                <button onClick={() => setSort('published_at')} className="flex items-center gap-1 hover:text-foreground transition-colors" aria-label="Sort by Published">
                  Published{sortKey === 'published_at' && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
                </button>
              </TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                  {posts.length === 0 ? 'No posts yet. Create your first post.' : 'No posts match your filters.'}
                </TableCell>
              </TableRow>
            ) : (
              sorted.map((post) => (
                <TableRow key={post.slug}>
                  <TableCell className="w-8">
                    <input
                      type="checkbox"
                      checked={selected.has(post.slug)}
                      onChange={() => toggleSelect(post.slug)}
                      className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                      aria-label={`Select ${post.title}`}
                    />
                  </TableCell>
                  <TableCell className="font-medium text-foreground">{post.title}</TableCell>
                  <TableCell>
                    <Badge variant={post.status === 'published' ? 'default' : 'secondary'}>
                      {post.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDate(post.published_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Button asChild variant="ghost" size="sm">
                        <Link to={`/admin/posts/${post.slug}/edit`}>
                          <Pencil className="mr-1 h-3.5 w-3.5" />
                          Edit
                        </Link>
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => handleDelete(post.slug)}
                      >
                        <Trash2 className="mr-1 h-3.5 w-3.5" />
                        Delete
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Bulk action toolbar */}
      {selected.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-background px-6 py-3 shadow-2xl">
          <span className="text-sm text-foreground">{selected.size} selected</span>
          <Button size="sm" onClick={() => handleBulkSetStatus('published')}>Publish</Button>
          <Button size="sm" variant="secondary" onClick={() => handleBulkSetStatus('draft')}>Unpublish</Button>
          <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={handleBulkDelete}>Delete</Button>
          <button onClick={() => setSelected(new Set())} className="text-sm text-muted-foreground hover:text-foreground transition-colors">Clear</button>
        </div>
      )}
    </div>
  );
}

export default AdminPostList;
