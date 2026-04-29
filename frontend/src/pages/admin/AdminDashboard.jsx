import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileText, Globe, PenLine } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import api from '@/lib/axios';

function StatCard({ icon: Icon, label, value }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-bold text-foreground">{value}</p>
      </CardContent>
    </Card>
  );
}

function AdminDashboard() {
  const [posts, setPosts] = useState([]);

  useEffect(() => {
    api.get('/api/posts/').then((res) => setPosts(res.data));
  }, []);

  const total = posts.length;
  const published = posts.filter((p) => p.status === 'published').length;
  const drafts = posts.filter((p) => p.status === 'draft').length;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Overview of your content</p>
        </div>
        <Button asChild size="sm">
          <Link to="/admin/posts/new">New Post</Link>
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard icon={FileText} label="Total Posts" value={total} />
        <StatCard icon={Globe} label="Published" value={published} />
        <StatCard icon={PenLine} label="Drafts" value={drafts} />
      </div>

      <div>
        <Button asChild variant="outline" size="sm">
          <Link to="/admin/posts">View all posts</Link>
        </Button>
      </div>
    </div>
  );
}

export default AdminDashboard;
