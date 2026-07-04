import { Routes, Route, Navigate, useParams } from 'react-router-dom'
import Layout from '@/components/layout/Layout'
import ChatDrawer from '@/components/ChatDrawer'
import Home from '@/pages/Home'
import Deals from '@/pages/Deals'
import Training from '@/pages/Training'
import Shoes from '@/pages/Shoes'
import Retailers from '@/pages/Retailers'
import MyShoes from '@/pages/MyShoes'
import ShoeDetail from '@/pages/ShoeDetail'
import ChatPage from '@/pages/ChatPage'
import Settings from '@/pages/Settings'
import SettingsSync from '@/pages/SettingsSync'

// Preserve the :id when redirecting the old /my-shoes/:id bookmark to /shoes/:id.
function RedirectShoeDetail() {
  const { id } = useParams()
  return <Navigate to={`/shoes/${id}`} replace />
}

export default function App() {
  return (
    <>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="training" element={<Training />} />
          <Route path="deals" element={<Deals />} />
          <Route path="shoes" element={<MyShoes />} />
          <Route path="shoes/:id" element={<ShoeDetail />} />
          <Route path="assistant" element={<ChatPage />} />

          {/* Settings: control room, re-homes the former Tracked Shoes + Retailers pages */}
          <Route path="settings" element={<Settings />}>
            <Route index element={<Navigate to="/settings/tracking" replace />} />
            <Route path="tracking" element={<Shoes />} />
            <Route path="retailers" element={<Retailers />} />
            <Route path="sync" element={<SettingsSync />} />
          </Route>

          {/* Redirects for old bookmarks (§1 route table) */}
          <Route path="my-shoes" element={<Navigate to="/shoes" replace />} />
          <Route path="my-shoes/:id" element={<RedirectShoeDetail />} />
          <Route path="retailers" element={<Navigate to="/settings/retailers" replace />} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
      <ChatDrawer />
    </>
  )
}
