import { lazyPage } from '@/components/lazyPage'
import { Routes, Route, Navigate, useParams } from 'react-router-dom'
import Layout from '@/components/layout/Layout'
import ChatDrawer from '@/components/ChatDrawer'
import { useMediaQuery } from '@/hooks/useMediaQuery'
// Home stays eager: it is the launch screen. Every other route page is split
// into its own chunk so the initial bundle only carries the shell + Home. The
// Suspense boundary lives in Layout around <Outlet />, so the nav stays mounted
// while a page chunk loads.
import Home from '@/pages/Home'
const Deals = lazyPage(() => import('@/pages/Deals'))
const Training = lazyPage(() => import('@/pages/Training'))
const Shoes = lazyPage(() => import('@/pages/Shoes'))
const Retailers = lazyPage(() => import('@/pages/Retailers'))
const NewRuns = lazyPage(() => import('@/pages/NewRuns'))
const MyShoes = lazyPage(() => import('@/pages/MyShoes'))
const ShoeDetail = lazyPage(() => import('@/pages/ShoeDetail'))
const ShoePipeline = lazyPage(() => import('@/pages/ShoePipeline'))
const ActivityDetail = lazyPage(() => import('@/pages/ActivityDetail'))
const ChatPage = lazyPage(() => import('@/pages/ChatPage'))
const Settings = lazyPage(() => import('@/pages/Settings'))
const SettingsSync = lazyPage(() => import('@/pages/SettingsSync'))

// Preserve the :id when redirecting the old /my-shoes/:id bookmark to /shoes/:id.
function RedirectShoeDetail() {
  const { id } = useParams()
  return <Navigate to={`/shoes/${id}`} replace />
}

export default function App() {
  // ChatDrawer's open button is md+ only, so on phones the drawer is unreachable.
  // Mount it only at md+ (768px) so its useChatStream and fixed overlay don't run
  // on phones. Desktop is unchanged.
  const isDesktop = useMediaQuery('(min-width: 768px)')
  return (
    <>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="training" element={<Training />} />
          <Route path="activities/:id" element={<ActivityDetail />} />
          <Route path="deals" element={<Deals />} />
          <Route path="new-runs" element={<NewRuns />} />
          <Route path="shoes" element={<MyShoes />} />
          <Route path="shoes/pipeline" element={<ShoePipeline />} />
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
      {isDesktop && <ChatDrawer />}
    </>
  )
}
