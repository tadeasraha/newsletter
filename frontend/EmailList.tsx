import React, { useEffect, useState } from "react";
// doporučeno: use DOMPurify pro sanitaci HTML před vložením
import DOMPurify from "dompurify";

type EmailItem = {
  id: string;
  subject: string;
  preview: string;
  summary_html: string; // bezpečné HTML z backendu
};

export default function EmailList() {
  const [emails, setEmails] = useState<EmailItem[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    // prefetch na mountu
    fetch("/api/emails/prefetch")
      .then((r) => r.json())
      .then((data: EmailItem[]) => setEmails(data))
      .catch((e) => console.error("Prefetch error", e));
  }, []);

  const toggle = (id: string) => {
    setExpanded((s) => ({ ...s, [id]: !s[id] }));
  };

  return (
    <div>
      {emails.map((e) => (
        <div key={e.id} style={{ borderBottom: "1px solid #ddd", padding: "12px 0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <strong>{e.subject}</strong>
              <div style={{ color: "#666", marginTop: 6 }}>{e.preview}</div>
            </div>
            <button onClick={() => toggle(e.id)}>{expanded[e.id] ? "Sbalit" : "Rozbalit"}</button>
          </div>

          {expanded[e.id] && (
            <div
              style={{ marginTop: 12 }}
              // bezpečně vlož HTML (backend by měl vracet sanitizované HTML; zde navíc DOMPurify)
              dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(e.summary_html) }}
            />
          )}
        </div>
      ))}
    </div>
  );
}
