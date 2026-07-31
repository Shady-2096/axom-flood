export const COPY_VERSION = 1;

const COPY = Object.freeze({
  responsibility_notice:
    "Axom Flood is a community reporting channel, not an emergency service. " +
    "No responder is monitoring this chat, and sending a report will not request rescue. " +
    "If anyone is in immediate danger, call the ASDMA State Emergency Operation Centre " +
    "on 1070 now. Calls require a mobile signal.",
  location_prompt:
    "Share the location where you are standing. The coordinate is rounded before it is saved.",
  depth_prompt: "Choose the closest water depth where you are now.",
  review:
    "Review the community report: {depth} at {place}. Submit only what you can see where you are.",
  emergency:
    "I have not sent a rescue request. Call 1070 now. Axom Flood currently has no verified " +
    "district, police, or ambulance directory; use locally issued numbers if you have them. " +
    "After calling, you may continue with a community flood report.",
  submitted:
    "Report saved for {place} at {time}. It contributes to community flood evidence only and " +
    "does not notify emergency responders. If anyone is in danger, call 1070.",
  cancelled: "The report was cancelled. Nothing was submitted.",
  expired: "This reporting session expired. Start again to submit a new observation.",
  invalid: "That answer does not match the current question. Please use one of the choices shown.",
  duplicate: "That message was already received.",
});

export function renderCopy(copyKey, parameters = {}) {
  const template = COPY[copyKey];
  if (!template) throw new Error(`unknown copy key: ${copyKey}`);
  return template.replace(/\{([a-z_]+)\}/g, (match, key) => {
    const value = parameters[key];
    return value == null ? match : String(value);
  });
}

export function copyKeys() {
  return Object.keys(COPY);
}
