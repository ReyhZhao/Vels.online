import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Server, Activity, Zap, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import PostCard from '@/components/blog/PostCard';
import api from '../lib/axios';

const SERVICES = [
  {
    id: 'infrastructure',
    icon: Server,
    title: 'Infrastructure',
    description:
      'Monitor and manage your infrastructure with real-time visibility across all your services and environments.',
  },
  {
    id: 'observability',
    icon: Activity,
    title: 'Observability',
    description:
      'Logs, metrics, and traces unified in one place so you can diagnose issues before they become incidents.',
  },
  {
    id: 'automation',
    icon: Zap,
    title: 'Automation',
    description:
      'Automate repetitive workflows and deployments to ship faster and reduce operational overhead.',
  },
];

function HeroSection() {
  return (
    <section className="relative flex flex-col items-center justify-center px-4 py-32 text-center">
      <div className="max-w-3xl space-y-6">
        <p className="text-sm font-semibold uppercase tracking-widest text-primary">
          vels.online
        </p>
        <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-5xl">
          Your Infrastructure,{' '}
          <span className="text-primary">Simplified</span>
        </h1>
        <p className="text-lg text-muted-foreground">
          Managed services, observability, and engineering insights from Eddie Vels.
          Built to scale with your needs.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
          <Button asChild size="lg">
            <Link to="/blog">View Blog</Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <a href="#services">
              Services <ArrowRight className="ml-1 h-4 w-4" />
            </a>
          </Button>
        </div>
      </div>
    </section>
  );
}

function ServicesSection() {
  return (
    <section id="services" className="border-t border-border px-4 py-20">
      <div className="container mx-auto">
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-bold tracking-tight text-foreground">Services</h2>
          <p className="mt-3 text-muted-foreground">
            Expanding capabilities — more coming soon.
          </p>
        </div>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {SERVICES.map(({ id, icon: Icon, title, description }) => (
            <Card key={id} className="flex flex-col">
              <CardHeader>
                <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-md bg-primary/10">
                  <Icon className="h-5 w-5 text-primary" />
                </div>
                <CardTitle className="text-base">{title}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">{description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}

function BlogPreviewSection({ posts }) {
  return (
    <section className="border-t border-border px-4 py-20">
      <div className="container mx-auto">
        <div className="mb-12 flex items-end justify-between">
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-foreground">
              Latest Posts
            </h2>
            <p className="mt-3 text-muted-foreground">
              Thoughts on engineering, infrastructure, and operations.
            </p>
          </div>
          <Link
            to="/blog"
            className="flex items-center gap-1 text-sm font-medium text-primary hover:underline"
          >
            View all posts <ArrowRight className="h-4 w-4" />
          </Link>
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
    </section>
  );
}

function LandingPage() {
  const [posts, setPosts] = useState([]);

  useEffect(() => {
    api.get('/api/posts/').then((res) => {
      setPosts(res.data.slice(0, 3));
    });
  }, []);

  return (
    <div>
      <HeroSection />
      <ServicesSection />
      <BlogPreviewSection posts={posts} />
    </div>
  );
}

export default LandingPage;
