import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from '@/components/layout/Layout'
import Dashboard from '@/pages/Dashboard'
import Deals from '@/pages/Deals'
import Shoes from '@/pages/Shoes'
import Retailers from '@/pages/Retailers'
import MyShoes from '@/pages/MyShoes'
import ShoeDetail from '@/pages/ShoeDetail'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="deals" element={<Deals />} />
        <Route path="shoes" element={<Shoes />} />
        <Route path="retailers" element={<Retailers />} />
        <Route path="my-shoes" element={<MyShoes />} />
        <Route path="my-shoes/:id" element={<ShoeDetail />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
