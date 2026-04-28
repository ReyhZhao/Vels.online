import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../lib/axios';

function AdminPostList() {
  const [posts, setPosts] = useState([]);

  const loadPosts = () => {
    api.get('/api/posts/').then((res) => setPosts(res.data));
  };

  useEffect(() => {
    loadPosts();
  }, []);

  const handleDelete = async (slug) => {
    if (!window.confirm('Delete this post?')) return;
    await api.delete(`/api/posts/${slug}/`);
    loadPosts();
  };

  return (
    <main>
      <h1>Posts</h1>
      <Link to="/admin/posts/new">New Post</Link>
      <ul>
        {posts.map((post) => (
          <li key={post.slug}>
            <span>{post.title}</span>
            <span>{post.status}</span>
            <Link to={`/admin/posts/${post.slug}/edit`}>Edit</Link>
            <button onClick={() => handleDelete(post.slug)}>Delete</button>
          </li>
        ))}
      </ul>
    </main>
  );
}

export default AdminPostList;
