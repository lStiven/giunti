import { useCallback, useEffect, useState, type ReactElement } from "react";

import { ApiRequestError } from "../api/client";
import { AlertIcon } from "../components/icons";
import { KeyLogin } from "../components/KeyLogin";
import { takeKeyFromUrl } from "../invite";
import { errorText } from "../messages";
import { ADMIN_KEY_ITEM, forgetKey, loadKey, saveKey } from "../storage";
import {
  createClient,
  listClients,
  deleteClient,
  replaceKey,
  updateClient,
  type ClientChanges,
  type ClientView,
  type IssuedKey,
  type NewClient,
} from "./api";
import { ClientCard } from "./ClientCard";
import { IssuedKeyCard } from "./IssuedKeyCard";
import { NewClientForm } from "./NewClientForm";

type Phase = "login" | "checking" | "ready";

const LOGIN_PROBLEMS: Record<string, string> = {
  UNAUTHENTICATED: "La clave no es válida. Revisa que la hayas copiado completa.",
  FORBIDDEN: "Esta clave no es de administrador o está desactivada.",
};

/**
 * The administrator's page (`/admin`): create clients and send them an invitation link,
 * deactivate them, change their limits and replace their key.
 */
export default function AdminApp(): ReactElement {
  const [adminKey, setAdminKey] = useState<string | null>(
    () => takeKeyFromUrl() ?? loadKey(ADMIN_KEY_ITEM),
  );
  const [phase, setPhase] = useState<Phase>(adminKey === null ? "login" : "checking");
  const [loginProblem, setLoginProblem] = useState<string | null>(null);
  const [clients, setClients] = useState<ClientView[]>([]);
  const [issued, setIssued] = useState<IssuedKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionProblem, setActionProblem] = useState<string | null>(null);

  const signOut = useCallback((problem: string | null): void => {
    forgetKey(ADMIN_KEY_ITEM);
    setAdminKey(null);
    setPhase("login");
    setLoginProblem(problem);
  }, []);

  useEffect(() => {
    if (phase !== "checking" || adminKey === null) {
      return;
    }
    listClients(adminKey).then(
      (loaded) => {
        saveKey(ADMIN_KEY_ITEM, adminKey);
        setClients(loaded);
        setPhase("ready");
      },
      (error: unknown) => {
        const code = error instanceof ApiRequestError ? error.code : "UNKNOWN";
        signOut(LOGIN_PROBLEMS[code] ?? describe(error));
      },
    );
  }, [phase, adminKey, signOut]);

  const run = async (action: (key: string) => Promise<void>): Promise<void> => {
    if (adminKey === null) {
      return;
    }
    setBusy(true);
    setActionProblem(null);
    try {
      await action(adminKey);
    } catch (error) {
      if (error instanceof ApiRequestError && error.code in LOGIN_PROBLEMS) {
        signOut(LOGIN_PROBLEMS[error.code] ?? null);
      } else {
        setActionProblem(describe(error));
      }
    } finally {
      setBusy(false);
    }
  };

  const replaceClient = (updated: ClientView): void => {
    setClients((current) => current.map((c) => (c.id === updated.id ? updated : c)));
  };

  const create = (client: NewClient): void => {
    void run(async (key) => {
      const created = await createClient(key, client);
      setClients((current) => [created.client, ...current]);
      setIssued(created);
    });
  };

  const change = (clientId: string, changes: ClientChanges): void => {
    void run(async (key) => {
      replaceClient(await updateClient(key, clientId, changes));
    });
  };

  const newInvitation = (client: ClientView): void => {
    const confirmed = window.confirm(
      `¿Generar una nueva invitación para ${client.name}? Su enlace y su clave actuales dejarán de funcionar.`,
    );
    if (confirmed) {
      void run(async (key) => {
        const replaced = await replaceKey(key, client.id);
        replaceClient(replaced.client);
        setIssued(replaced);
      });
    }
  };

  const remove = (client: ClientView): void => {
    const confirmed = window.confirm(
      `¿Eliminar a ${client.name}? Su enlace y su clave dejarán de funcionar y se borrará su historial de uso. No se puede deshacer.`,
    );
    if (confirmed) {
      void run(async (key) => {
        await deleteClient(key, client.id);
        setClients((current) => current.filter((c) => c.id !== client.id));
        setIssued((current) => (current?.client.id === client.id ? null : current));
      });
    }
  };

  return (
    <div className="page page--wide">
      <header className="hero hero--compact">
        <p className="hero__eyebrow">Administración</p>
        <h1 className="hero__title">Clientes y accesos</h1>
        <p className="hero__lead">
          Crea un cliente y envíale su enlace de invitación: con un clic podrá usar el servicio.
        </p>
      </header>

      <main className="panel">
        {phase === "ready" ? (
          <div className="admin">
            {issued ? (
              <IssuedKeyCard
                issued={issued}
                onDone={() => {
                  setIssued(null);
                }}
              />
            ) : (
              <section className="admin__section" aria-labelledby="new-client-title">
                <h2 className="admin__title" id="new-client-title">
                  Nuevo cliente
                </h2>
                <NewClientForm busy={busy} onCreate={create} />
              </section>
            )}

            {actionProblem && (
              <div className="notice notice--error" role="alert">
                <span className="notice__icon">
                  <AlertIcon />
                </span>
                <p className="notice__body">{actionProblem}</p>
              </div>
            )}

            <section className="admin__section" aria-labelledby="clients-title">
              <div className="admin__heading">
                <h2 className="admin__title" id="clients-title">
                  Clientes ({clients.length})
                </h2>
                <button
                  type="button"
                  className="link-button"
                  onClick={() => {
                    signOut(null);
                  }}
                >
                  Cerrar sesión
                </button>
              </div>
              <ul className="clients">
                {clients.map((client) => (
                  <ClientCard
                    key={client.id}
                    client={client}
                    busy={busy}
                    onChange={(changes) => {
                      change(client.id, changes);
                    }}
                    onNewInvitation={() => {
                      newInvitation(client);
                    }}
                    onDelete={() => {
                      remove(client);
                    }}
                  />
                ))}
              </ul>
            </section>
          </div>
        ) : (
          <section className="admin__login" aria-labelledby="login-title">
            <h2 className="step__title" id="login-title">
              Acceso de administrador
            </h2>
            <p className="step__help">
              Abre el enlace de administrador que se generó al instalar el servicio, o pega aquí la
              clave.
            </p>
            <KeyLogin
              label="Clave de administrador"
              checking={phase === "checking"}
              problem={loginProblem}
              onSubmit={(key) => {
                setLoginProblem(null);
                setAdminKey(key);
                setPhase("checking");
              }}
            />
          </section>
        )}
      </main>
    </div>
  );
}

function describe(error: unknown): string {
  if (error instanceof ApiRequestError) {
    const text = errorText(error.code, error.retryAfterSeconds);
    return `${text.title}. ${text.hint}`;
  }
  return errorText("UNKNOWN").title;
}
