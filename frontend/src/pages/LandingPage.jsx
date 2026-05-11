import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Server, Activity, Zap, ArrowRight, ShieldCheck, AlertTriangle, ListChecks, Users, Lock, Clock, Globe } from 'lucide-react';
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
  {
    id: 'managed-security',
    icon: ShieldCheck,
    title: 'Managed Security',
    description:
      'End-to-end security incident management for your organisation, handled by our SOC team with full transparency and auditability.',
  },
];

const MSSP_FEATURES = [
  {
    icon: AlertTriangle,
    title: 'Incident triage and response',
    description:
      'Incoming incidents are assigned, prioritised by severity, and worked to resolution by dedicated SOC analysts.',
  },
  {
    icon: ListChecks,
    title: 'Playbook enforcement',
    description:
      'Subject-based task templates automatically apply the right checklist for each incident type — phishing, malware, vulnerability, and more.',
  },
  {
    icon: Users,
    title: 'Delegation and transfers',
    description:
      'Analysts can temporarily delegate work to teammates and receive it back when done, maintaining a clear chain of responsibility.',
  },
  {
    icon: Lock,
    title: 'TLP/PAP-aware communications',
    description:
      'Sensitive findings are gated by classification level — customers see exactly what they are entitled to see, nothing more.',
  },
  {
    icon: Clock,
    title: 'Full audit trail',
    description:
      'Every state change, comment, delegation, and attachment is timestamped in an immutable timeline for complete accountability.',
  },
  {
    icon: Globe,
    title: 'Multi-organisation support',
    description:
      "Each customer organisation's incidents are isolated and managed independently, with no cross-tenant data leakage.",
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
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-2">
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

function ManagedSecuritySection() {
  return (
    <section className="border-t border-border px-4 py-20">
      <div className="container mx-auto">
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-bold tracking-tight text-foreground">
            Managed Security Services
          </h2>
          <p className="mt-3 mx-auto max-w-2xl text-muted-foreground">
            Our SOC team handles the full lifecycle of security incident management for your
            organisation — triaging, tracking, and resolving incidents with full playbook
            enforcement and an immutable audit trail.
          </p>
        </div>
        <div className="grid gap-8 sm:grid-cols-2">
          {MSSP_FEATURES.map(({ icon: Icon, title, description }) => (
            <div key={title} className="flex gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10">
                <Icon className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-foreground">{title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{description}</p>
              </div>
            </div>
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
      <ManagedSecuritySection />
      <BlogPreviewSection posts={posts} />
    </div>
  );
}

export default LandingPage;
