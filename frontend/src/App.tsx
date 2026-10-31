import { AppRoutes } from "@/app/routes";
import { SessionGate } from "@/app/SessionGate";
import { ChatProvider } from "@/features/chat/ChatProvider";
import { ChatViewProvider } from "@/features/chat/ChatViewProvider";
import {
  EventStreamProvider,
  type EventSourceFactory,
} from "@/features/events/EventStreamProvider";
import { ThemeProvider } from "@/lib/theme";

/** App root. Expects a router and a QueryClientProvider above it (see main.tsx). */
export function App({ eventSourceFactory }: { eventSourceFactory?: EventSourceFactory }) {
  return (
    <ThemeProvider>
      <SessionGate>
        <EventStreamProvider factory={eventSourceFactory}>
          <ChatViewProvider>
            <ChatProvider>
              <AppRoutes />
            </ChatProvider>
          </ChatViewProvider>
        </EventStreamProvider>
      </SessionGate>
    </ThemeProvider>
  );
}
