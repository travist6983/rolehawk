import { Route, Routes } from "react-router";

import { PipelinePage } from "@/routes/pipeline";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<PipelinePage />} />
    </Routes>
  );
}
