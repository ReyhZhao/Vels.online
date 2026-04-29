import { Outlet } from 'react-router-dom';
import TopNav from './TopNav';
import Footer from './Footer';

function PublicLayout() {
  return (
    <div className="flex min-h-screen flex-col">
      <TopNav />
      <main className="flex-1">
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}

export default PublicLayout;
