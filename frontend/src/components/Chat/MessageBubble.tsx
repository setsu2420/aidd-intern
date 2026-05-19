import { memo } from 'react';
import UserMessage from './UserMessage';
import AssistantMessage from './AssistantMessage';
import type { UIMessage } from 'ai';
import type { MessageMeta } from '@/types/agent';

interface MessageBubbleProps {
  message: UIMessage;
  isLastTurn?: boolean;
  onUndoTurn?: () => void;
  onEditAndRegenerate?: (messageId: string, newText: string) => void | Promise<void>;
  isProcessing?: boolean;
  isStreaming?: boolean;
  sessionId?: string | null;
  approveTools: (approvals: Array<{ tool_call_id: string; approved: boolean; feedback?: string | null }>) => Promise<boolean>;
}

function sameMessageParts(prevParts: UIMessage['parts'], nextParts: UIMessage['parts']): boolean {
  if (prevParts === nextParts) return true;
  if (prevParts.length !== nextParts.length) return false;

  for (let i = 0; i < prevParts.length; i++) {
    const prevPart = prevParts[i];
    const nextPart = nextParts[i];

    if (prevPart === nextPart) continue;
    if (prevPart.type !== nextPart.type) return false;

    if (prevPart.type === 'text' && nextPart.type === 'text') {
      if (prevPart.text !== nextPart.text) return false;
      continue;
    }

    if (prevPart.type === 'dynamic-tool' && nextPart.type === 'dynamic-tool') {
      if (
        prevPart.toolCallId !== nextPart.toolCallId ||
        prevPart.toolName !== nextPart.toolName ||
        prevPart.state !== nextPart.state
      ) {
        return false;
      }
      if (!Object.is(prevPart.input, nextPart.input)) return false;
      if (!Object.is(prevPart.output, nextPart.output)) return false;
      if (!Object.is(prevPart.errorText, nextPart.errorText)) return false;
      const prevApprovalId = prevPart.approval?.id ?? null;
      const nextApprovalId = nextPart.approval?.id ?? null;
      if (prevApprovalId !== nextApprovalId) return false;
      continue;
    }

    if (!Object.is(prevPart, nextPart)) return false;
  }

  return true;
}

function MessageBubble({
  message,
  isLastTurn = false,
  onUndoTurn,
  onEditAndRegenerate,
  isProcessing = false,
  isStreaming = false,
  sessionId,
  approveTools,
}: MessageBubbleProps) {
  if (message.role === 'user') {
    return (
      <UserMessage
        message={message}
        isLastTurn={isLastTurn}
        onUndoTurn={onUndoTurn}
        onEditAndRegenerate={onEditAndRegenerate}
        isProcessing={isProcessing}
      />
    );
  }

  if (message.role === 'assistant') {
    return (
      <AssistantMessage
        message={message}
        isStreaming={isStreaming}
        sessionId={sessionId}
        approveTools={approveTools}
      />
    );
  }

  return null;
}

function areMessageBubblePropsEqual(prev: MessageBubbleProps, next: MessageBubbleProps): boolean {
  return (
    prev.isLastTurn === next.isLastTurn &&
    prev.isProcessing === next.isProcessing &&
    prev.isStreaming === next.isStreaming &&
    prev.sessionId === next.sessionId &&
    prev.onUndoTurn === next.onUndoTurn &&
    prev.onEditAndRegenerate === next.onEditAndRegenerate &&
    prev.approveTools === next.approveTools &&
    prev.message.id === next.message.id &&
    prev.message.role === next.message.role &&
    ((prev.message.metadata as MessageMeta | undefined)?.createdAt ?? null) ===
      ((next.message.metadata as MessageMeta | undefined)?.createdAt ?? null) &&
    sameMessageParts(prev.message.parts, next.message.parts)
  );
}

export default memo(MessageBubble, areMessageBubblePropsEqual);
