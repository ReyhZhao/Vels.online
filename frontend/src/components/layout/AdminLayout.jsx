import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

function AdminLayout() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex flex-1 flex-col bg-background">
        <Outlet />
      </div>
    </div>
  );
}

export default AdminLayout;
