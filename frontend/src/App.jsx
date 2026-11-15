import { Navigate, Route, Routes } from 'react-router-dom';
import AppShell from './components/AppShell.jsx';
import LandingPage from './components/LandingPage.jsx';
import PublicDemo from './components/PublicDemo.jsx';
import { AboutPage, AdvisoryPage, AssessmentPage, AuthPage, CropPage, DashboardPage, FarmProfilePage, HistoryPage, IrrigationPage, SettingsPage, SoilPage, WeatherPage } from './components/Pages.jsx';
import { useFarm } from './context/FarmContext.jsx';

function Inside({ children }) {
  const { credentialFarmId, account, accountLoading } = useFarm();
  if (accountLoading) return <p className="loading-note">Checking your account session…</p>;
  return credentialFarmId || account ? <AppShell>{children}</AppShell> : <Navigate to="/login" replace />;
}

export default function App() {
  return <Routes>
    <Route path="/" element={<LandingPage />} />
    <Route path="/login" element={<AuthPage />} />
    <Route path="/signup" element={<AuthPage signup />} />
    <Route path="/about" element={<AboutPage />} />
    <Route path="/demo" element={<PublicDemo />} />
    <Route path="/demo/:section" element={<PublicDemo />} />
    <Route path="/dashboard" element={<Inside><DashboardPage /></Inside>} />
    <Route path="/farm" element={<Inside><FarmProfilePage /></Inside>} />
    <Route path="/assessment" element={<Inside><AssessmentPage /></Inside>} />
    <Route path="/weather" element={<Inside><WeatherPage /></Inside>} />
    <Route path="/soil" element={<Inside><SoilPage /></Inside>} />
    <Route path="/crop" element={<Inside><CropPage /></Inside>} />
    <Route path="/irrigation" element={<Inside><IrrigationPage /></Inside>} />
    <Route path="/advisory" element={<Inside><AdvisoryPage /></Inside>} />
    <Route path="/history" element={<Inside><HistoryPage /></Inside>} />
    <Route path="/settings" element={<Inside><SettingsPage /></Inside>} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>;
}
