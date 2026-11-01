// Runs inside the application page (Playwright page.evaluate). Tags each fillable field
// with the applicant key it matches, using its visible label first, then name, id,
// placeholder, and autocomplete hints. The first matching rule wins; each text key is used
// once. Returns every field so the caller can report required ones left empty.
() => {
  const rules = [
    ["first_name", /\b(first|given)\s*name\b|^first$/],
    ["last_name", /\b(last|family)\s*name\b|surname|^last$/],
    ["email", /e-?mail/],
    ["phone", /phone|mobile|telephone/],
    ["linkedin", /linkedin/],
    ["github", /github/],
    ["website", /website|portfolio|personal (site|url)/],
    ["location", /^(current )?location\b|^city\b|where are you (based|located)/],
    ["resume", /resume|\bcv\b|curriculum/],
    ["cover_letter", /cover\s*letter/],
    ["full_name", /^(full |legal |your )?name\b/],
  ];
  const textOf = (el) => (el ? el.textContent || "" : "").replace(/\s+/g, " ").trim();
  const labelFor = (el) => {
    const parts = [];
    if (el.id) document.querySelectorAll(`label[for="${CSS.escape(el.id)}"]`).forEach(l => parts.push(textOf(l)));
    const wrap = el.closest("label");
    if (wrap) parts.push(textOf(wrap));
    const by = el.getAttribute("aria-labelledby");
    if (by) by.split(/\s+/).forEach(id => parts.push(textOf(document.getElementById(id))));
    parts.push(el.getAttribute("aria-label") || "", el.getAttribute("placeholder") || "");
    return parts.filter(Boolean).join(" ").replace(/[*✱]/g, "").trim();
  };
  const used = new Set();
  const fields = [];
  const els = document.querySelectorAll("input, textarea");
  els.forEach((el, index) => {
    const type = (el.getAttribute("type") || el.tagName).toLowerCase();
    if (["hidden", "submit", "button", "checkbox", "radio", "reset", "image", "search"].includes(type)) return;
    const label = labelFor(el);
    const hint = [label, el.name || "", el.id || "", el.getAttribute("autocomplete") || ""].join(" ").toLowerCase();
    let key = null;
    if (type === "email") key = "email";
    else if (type === "tel") key = "phone";
    else if (type === "file") key = /cover/.test(hint) ? "cover_letter" : (/resume|\bcv\b|curriculum|attach/.test(hint) ? "resume" : null);
    else {
      const labelText = label.toLowerCase();
      for (const [name, pattern] of rules) {
        if (name === "resume") continue;
        if (pattern.test(labelText) || (!labelText && pattern.test(hint))) { key = name; break; }
      }
    }
    const required = el.required || el.getAttribute("aria-required") === "true" || /\*|✱|required/.test(label);
    if (key && (type === "file" || !used.has(key))) {
      if (type !== "file") used.add(key);
      el.setAttribute("data-rolehawk-key", key);
      el.setAttribute("data-rolehawk-index", String(index));
    }
    fields.push({ key: key && el.getAttribute("data-rolehawk-key") === key ? key : null,
                  label: label || el.name || el.id || type, type, required,
                  index, empty: !el.value });
  });
  return fields;
}
