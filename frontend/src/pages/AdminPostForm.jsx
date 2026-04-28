import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
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
    navigate('/admin/');
  };

  return (
    <main>
      <h1>{isEditing ? 'Edit Post' : 'New Post'}</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Title
          <input name="title" value={form.title} onChange={handleChange} />
        </label>
        <label>
          Content
          <textarea name="content" value={form.content} onChange={handleChange} />
        </label>
        <label>
          Status
          <select name="status" value={form.status} onChange={handleChange}>
            <option value="draft">Draft</option>
            <option value="published">Published</option>
          </select>
        </label>
        <button type="submit">{isEditing ? 'Save' : 'Create'}</button>
      </form>
    </main>
  );
}

export default AdminPostForm;
