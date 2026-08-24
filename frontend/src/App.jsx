import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, Protected } from './auth'
import { RealtimeProvider } from './realtime'
import { Layout } from './components'
const Login = lazy(() => import('./pages/AuthPages').then((module) => ({ default: module.Login })))
const Register = lazy(() => import('./pages/AuthPages').then((module) => ({ default: module.Register })))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const resource = (name) => lazy(() => import('./pages/Resources').then((module) => ({ default: module[name] })))
const Agents = resource('Agents'), Alerts = resource('Alerts'), Anomalies = resource('Anomalies'), Audit = resource('Audit')
const HyperV = resource('HyperV'), HyperVDetail = resource('HyperVDetail'), MachineDetail = resource('MachineDetail'), Machines = resource('Machines')
const ML = resource('ML'), SettingsPage = resource('SettingsPage'), Users = resource('Users'), VMware = resource('VMware'), VMwareDetail = resource('VMwareDetail')

function SecuredLayout() { return <Protected><RealtimeProvider><Layout /></RealtimeProvider></Protected> }

export default function App() {
  return <AuthProvider><Suspense fallback={<div className="center-state"><span className="spinner" />Chargement du module…</div>}><Routes>
    <Route path="/login" element={<Login />} /><Route path="/register" element={<Register />} />
    <Route element={<SecuredLayout />}>
      <Route path="/dashboard" element={<Dashboard />} /><Route path="/machines" element={<Machines />} /><Route path="/machines/:id" element={<MachineDetail />} />
      <Route path="/agents" element={<Agents />} /><Route path="/alerts" element={<Alerts />} /><Route path="/anomalies" element={<Anomalies />} />
      <Route path="/vmware" element={<VMware />} /><Route path="/vmware/:id" element={<VMwareDetail />} /><Route path="/hyperv" element={<HyperV />} /><Route path="/hyperv/:id" element={<HyperVDetail />} />
      <Route path="/ml" element={<ML />} /><Route path="/users" element={<Users />} /><Route path="/settings" element={<SettingsPage />} /><Route path="/audit" element={<Audit />} />
    </Route>
    <Route path="/" element={<Navigate to="/dashboard" replace />} /><Route path="*" element={<Navigate to="/dashboard" replace />} />
  </Routes></Suspense></AuthProvider>
}
