"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export function PromoteExemplarButton({ runId }: { runId: string }) {
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");

  async function handleClick() {
    setState("saving");
    try {
      await api.promoteExemplar(runId);
      setState("saved");
      setTimeout(() => setState("idle"), 2500);
    } catch {
      setState("idle");
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={state !== "idle"}
      className="btn text-sm"
      style={state === "saved" ? { color: "var(--green)", borderColor: "var(--green)" } : {}}
    >
      {state === "saved" ? "Saved!" : state === "saving" ? "Saving…" : "Save as Exemplar"}
    </button>
  );
}
