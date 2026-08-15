import type { ChatResponse } from "./types";

/** Customer-facing labels. Operator strip still shows contract field names. */
export const UI = {
  askHeading: "Tell us what you need help with.",
  askHelp: "",
  questionLabel: "Your question",
  talkToHuman: "I'd rather talk to a person",
  send: "Get help",
  sending: "Looking that up…",
  emptyError: "Please type a question so we can help.",
  tooLongError: "Please keep your question under 4000 characters.",
  statusHeading: "Status",
  lastUpdated: "Updated",
  reference: "Reference",
  chatHeading: "Chat",
  chatHelp: "Your messages are on the right; B-Mobile replies on the left.",
  chatEmpty: "Type a question below to start. Try asking how to reset your My Account PIN.",
  newConversation: "Start new conversation",
  sourcesHeading: "From our help articles",
  escalateNotice:
    "We're connecting you with a B-Mobile specialist. Live chat isn't available in this demo yet.",
  specialistNotes: "Notes for the specialist",
  historyHeading: "Recent questions",
  historyHelp: "Only saved in this browser tab. Refreshing the page clears the list.",
  historyEmpty: "No questions in this visit yet.",
  comingLater: "Coming later",
} as const;

export const CREW_STATUS_LABEL = {
  idle: "Ready",
  running: "Looking that up",
  done: "Finished",
  error: "Couldn't finish",
} as const;

export function outcomeLabel(decision: ChatResponse["decision"]): string {
  return decision === "escalate" ? "Sent to a specialist" : "Answered";
}
