import type { GatewayClient } from "@/lib/gatewayClient";
import type { RpcSender } from "./hooks/useSessions";

/** The chat's `sendRpc` dressed as the GatewayClient that the shared dialogs and
 *  the slash popover take (they only ever call `request`). */
export function rpcGatewayClient(sendRpc: RpcSender): GatewayClient {
  return {
    request: (method: string, params?: Record<string, unknown>) => sendRpc(method, params),
  } as unknown as GatewayClient;
}
