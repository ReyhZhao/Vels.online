import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const EXCERPT_LENGTH = 150;

function formatDate(dateStr) {
  if (!dateStr) return null;
  return new Date(dateStr).toLocaleDateString('en-AU', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

function PostCard({ title, slug, publishedAt, content }) {
  const excerpt =
    content && content.length > EXCERPT_LENGTH
      ? content.slice(0, EXCERPT_LENGTH) + '…'
      : content;

  return (
    <Card className="flex flex-col transition-colors hover:bg-accent/50">
      <CardHeader>
        <CardTitle className="text-base leading-snug">
          <Link to={`/${slug}`} className="hover:text-primary transition-colors">
            {title}
          </Link>
        </CardTitle>
        {publishedAt && (
          <p className="text-xs text-muted-foreground">{formatDate(publishedAt)}</p>
        )}
      </CardHeader>
      {excerpt && (
        <CardContent>
          <p className="text-sm text-muted-foreground leading-relaxed">{excerpt}</p>
        </CardContent>
      )}
    </Card>
  );
}

export default PostCard;
