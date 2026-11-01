/** The design's page header: a large serif title, a one-line note beside it, actions on the
 *  right. */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end gap-x-6 gap-y-3 px-5 pt-7 pb-5 md:px-8">
      <h1 className="font-serif text-4xl leading-none font-medium tracking-[-0.02em] md:text-[44px]">
        {title}
      </h1>
      {description && (
        <p className="mb-1 text-base leading-snug text-foreground-2">{description}</p>
      )}
      {actions && <div className="ml-auto flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
