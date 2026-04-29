import { useEffect, useState } from 'react';
import api from '../lib/axios';
import PostCard from '@/components/blog/PostCard';

function BlogIndexPage() {
  const [posts, setPosts] = useState([]);

  useEffect(() => {
    api.get('/api/posts/').then((res) => setPosts(res.data));
  }, []);

  return (
    <div className="container mx-auto px-4 py-12">
      <div className="mb-10">
        <h1 className="text-4xl font-bold tracking-tight text-foreground">Blog</h1>
        <p className="mt-3 text-muted-foreground">
          Thoughts on engineering, infrastructure, and operations.
        </p>
      </div>
      {posts.length === 0 ? (
        <p className="text-muted-foreground">No posts yet — check back soon.</p>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {posts.map((post) => (
            <PostCard
              key={post.slug}
              title={post.title}
              slug={post.slug}
              publishedAt={post.published_at}
              content={post.content}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default BlogIndexPage;
