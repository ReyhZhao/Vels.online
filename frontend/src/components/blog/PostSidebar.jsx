import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '@/lib/axios';

function readTime(content) {
  if (!content || !content.trim()) return 1;
  const wordCount = content.trim().split(/\s+/).length;
  return Math.ceil(wordCount / 200);
}

function formatDate(dateStr) {
  if (!dateStr) return null;
  return new Date(dateStr).toLocaleDateString('en-AU', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

function PostSidebar({ publishedAt, content, currentSlug }) {
  const [recentPosts, setRecentPosts] = useState([]);

  useEffect(() => {
    api.get('/api/posts/').then((res) => {
      setRecentPosts(
        res.data.filter((p) => p.slug !== currentSlug).slice(0, 5)
      );
    });
  }, [currentSlug]);

  const minutes = readTime(content);

  return (
    <aside className="space-y-4">
      <div className="rounded-lg border border-border bg-card p-4 space-y-4">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Post Info
        </h2>
        {publishedAt && (
          <div>
            <p className="text-xs text-muted-foreground">Published</p>
            <p className="text-sm text-foreground">{formatDate(publishedAt)}</p>
          </div>
        )}
        <div>
          <p className="text-xs text-muted-foreground">Read time</p>
          <p className="text-sm text-foreground">{minutes} min read</p>
        </div>
      </div>

      {recentPosts.length > 0 && (
        <div className="rounded-lg border border-border bg-card p-4 space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Recent Posts
          </h2>
          <ul className="space-y-2">
            {recentPosts.map((post) => (
              <li key={post.slug}>
                <Link
                  to={`/${post.slug}`}
                  className="text-sm text-muted-foreground hover:text-foreground transition-colors line-clamp-2"
                >
                  {post.title}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  );
}

export default PostSidebar;
