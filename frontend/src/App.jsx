import { Routes, Route } from 'react-router-dom';
import PostList from './pages/PostList';
import PostDetail from './pages/PostDetail';
import AdminPostList from './pages/AdminPostList';
import AdminPostForm from './pages/AdminPostForm';
import ProtectedRoute from './components/ProtectedRoute';

function App() {
  return (
    <Routes>
      <Route path="/" element={<PostList />} />
      <Route path="/admin" element={<ProtectedRoute><AdminPostList /></ProtectedRoute>} />
      <Route path="/admin/posts/new" element={<ProtectedRoute><AdminPostForm /></ProtectedRoute>} />
      <Route path="/admin/posts/:slug/edit" element={<ProtectedRoute><AdminPostForm /></ProtectedRoute>} />
      <Route path="/:slug" element={<PostDetail />} />
    </Routes>
  );
}

export default App;
