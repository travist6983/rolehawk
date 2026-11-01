import { useTheme, type ResolvedTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

const OPTIONS: { value: ResolvedTheme; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

/** The design's Light / Dark switch. Until one is picked, the app follows the OS. */
export function ThemeToggle() {
  const { resolved, setPreference } = useTheme();
  return (
    <span
      role="group"
      aria-label="Theme"
      className="flex gap-0.5 rounded-full bg-sidebar-active p-0.5"
    >
      {OPTIONS.map(({ value, label }) => {
        const on = resolved === value;
        return (
          <button
            key={value}
            type="button"
            aria-pressed={on}
            onClick={() => {
              setPreference(value);
            }}
            className={cn(
              "cursor-pointer rounded-full px-[7px] py-[3px] text-[12.5px] font-medium",
              on ? "bg-sidebar-foreground text-sidebar" : "text-sidebar-muted",
            )}
          >
            {label}
          </button>
        );
      })}
    </span>
  );
}
