import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { stripMarkdown } from '@/lib/utils';

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
  const plain = stripMarkdown(content);
  const excerpt =
    plain && plain.length > EXCERPT_LENGTH
      ? plain.slice(0, EXCERPT_LENGTH) + '…'
      : plain;

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
