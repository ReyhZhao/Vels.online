import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../lib/axios';
import MarkdownRenderer from '@/components/blog/MarkdownRenderer';
import PostSidebar from '@/components/blog/PostSidebar';

function PostDetail() {
  const { slug } = useParams();
  const [post, setPost] = useState(null);

  useEffect(() => {
    api.get(`/api/posts/${slug}/`).then((res) => setPost(res.data));
  }, [slug]);

  if (!post) return null;

  return (
    <div className="container mx-auto px-4 py-12">
      <h1 className="mb-8 text-4xl font-bold tracking-tight text-foreground">
        {post.title}
      </h1>
      <div className="grid grid-cols-1 gap-10 lg:grid-cols-[1fr_280px]">
        <MarkdownRenderer content={post.content} />
        <PostSidebar
          publishedAt={post.published_at}
          content={post.content}
          currentSlug={post.slug}
        />
      </div>
    </div>
  );
}

export default PostDetail;
