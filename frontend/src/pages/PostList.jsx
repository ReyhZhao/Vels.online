import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../lib/axios';

function PostList() {
  const [posts, setPosts] = useState([]);

  useEffect(() => {
    api.get('/api/posts/').then((res) => setPosts(res.data));
  }, []);

  return (
    <main>
      <h1>Blog</h1>
      <ul>
        {posts.map((post) => (
          <li key={post.slug}>
            <Link to={`/${post.slug}`}>{post.title}</Link>
          </li>
        ))}
      </ul>
    </main>
  );
}

export default PostList;
