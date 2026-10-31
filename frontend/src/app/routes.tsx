import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router";

import {
  BoardSkeleton,
  CardGridSkeleton,
  ChartSkeleton,
  DocumentSkeleton,
  FormSkeleton,
  TableSkeleton,
} from "@/components/feedback/Skeletons";

import { AppShell } from "./AppShell";

// Each screen is its own chunk; its skeleton shows while the code (and then data) loads.
const PipelinePage = lazy(() => import("@/features/pipeline/PipelinePage"));
const ProfilePage = lazy(() => import("@/features/profile/ProfilePage"));
const SettingsPage = lazy(() => import("@/features/settings/SettingsPage"));
const SourcesPage = lazy(() => import("@/features/sources/SourcesPage"));
const OnboardingPage = lazy(() => import("@/features/setup/OnboardingPage"));
const placeholders = () => import("@/features/placeholders");
const DiscoverPage = lazy(() => placeholders().then((m) => ({ default: m.DiscoverPage })));
const InsightsPage = lazy(() => placeholders().then((m) => ({ default: m.InsightsPage })));
const NotFoundPage = lazy(() => placeholders().then((m) => ({ default: m.NotFoundPage })));

function screen(element: React.ReactNode, fallback: React.ReactNode) {
  return <Suspense fallback={fallback}>{element}</Suspense>;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={screen(<PipelinePage />, <BoardSkeleton />)} />
        <Route path="discover" element={screen(<DiscoverPage />, <TableSkeleton />)} />
        <Route path="profile" element={screen(<ProfilePage />, <DocumentSkeleton />)} />
        <Route path="sources" element={screen(<SourcesPage />, <CardGridSkeleton />)} />
        <Route path="insights" element={screen(<InsightsPage />, <ChartSkeleton />)} />
        <Route path="settings" element={screen(<SettingsPage />, <FormSkeleton />)} />
        <Route path="onboarding" element={screen(<OnboardingPage />, <FormSkeleton />)} />
        <Route path="*" element={screen(<NotFoundPage />, null)} />
      </Route>
    </Routes>
  );
}
