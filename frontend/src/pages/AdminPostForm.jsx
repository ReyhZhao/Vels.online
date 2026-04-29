import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import api from '../lib/axios';

const EMPTY_FORM = { title: '', content: '', status: 'draft' };

function AdminPostForm() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const isEditing = !!slug;

  const [form, setForm] = useState(EMPTY_FORM);

  useEffect(() => {
    if (isEditing) {
      api.get(`/api/posts/${slug}/`).then((res) => {
        const { title, content, status } = res.data;
        setForm({ title, content, status });
      });
    }
  }, [slug, isEditing]);

  const handleChange = (e) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (isEditing) {
      await api.patch(`/api/posts/${slug}/`, form);
    } else {
      await api.post('/api/posts/', form);
    }
    navigate('/admin/posts');
  };

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <div>
        <p className="text-sm text-muted-foreground">
          Posts / {isEditing ? 'Edit' : 'New'}
        </p>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          {isEditing ? 'Edit Post' : 'New Post'}
        </h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="title">Title</Label>
          <Input
            id="title"
            name="title"
            value={form.title}
            onChange={handleChange}
            placeholder="Post title"
            required
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="content">Content</Label>
          <Textarea
            id="content"
            name="content"
            value={form.content}
            onChange={handleChange}
            placeholder="Write your post in Markdown..."
            rows={20}
            className="font-mono text-sm resize-y"
          />
          <p className="text-xs text-muted-foreground">
            Markdown is supported — headings, bold, code blocks, lists, and more.
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="status">Status</Label>
          <select
            id="status"
            name="status"
            value={form.status}
            onChange={handleChange}
            className={cn(
              'flex h-9 w-full rounded-md border border-input bg-background px-3 py-1',
              'text-sm text-foreground shadow-sm transition-colors',
              'focus:outline-none focus:ring-1 focus:ring-ring',
              'disabled:cursor-not-allowed disabled:opacity-50'
            )}
          >
            <option value="draft">Draft</option>
            <option value="published">Published</option>
          </select>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <Button type="submit">
            {isEditing ? 'Save' : 'Create'}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate('/admin/posts')}
          >
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
}

export default AdminPostForm;
