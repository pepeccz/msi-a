/**
 * Hardcoded quick-reply chips for the inbox message composer.
 *
 * Design decision A9: texts are neutral (no {admin_name} placeholder) so any
 * admin can use them without client-side substitution.
 */

export interface QuickReply {
  label: string;
  text: string;
}

export const QUICK_REPLIES: readonly QuickReply[] = [
  {
    label: "Saludo cordial",
    text: "Hola, soy del equipo de MSI Automotive. ",
  },
  {
    label: "Pedir documento",
    text: "Necesito que me envíes el siguiente documento: ",
  },
  {
    label: "Confirmar recepción",
    text: "Hemos recibido tu documentación, la revisamos en breve. ",
  },
  {
    label: "Disculpa por demora",
    text: "Disculpa la demora en la respuesta. ",
  },
  {
    label: "Política de plazos",
    text: "Los plazos habituales de homologación son de 5 a 10 días hábiles. ",
  },
  {
    label: "Despedida",
    text: "Gracias por confiar en MSI Automotive. Si necesitás algo más, escribinos cuando quieras.",
  },
] as const;
