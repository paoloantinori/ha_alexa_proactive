import crypto from 'crypto';

// Set as Lambda environment variables: the Client Id and Client Secret shown
// on the skill's PERMISSIONS page after enabling "Send Alexa Events".
const PERMISSIONS_CLIENT_ID = process.env.PERMISSIONS_CLIENT_ID ?? '';
const PERMISSIONS_CLIENT_SECRET = process.env.PERMISSIONS_CLIENT_SECRET ?? '';

const ENDPOINT = {
  endpointId: 'lavatrice-prova-001',
  manufacturerName: 'Sperimento HA',
  description: 'Lavatrice di prova (POC notifiche)',
  friendlyName: 'Lavatrice Prova',
  displayCategories: ['WASHER'],
  cookie: {},
  capabilities: [
    {
      type: 'AlexaInterface', interface: 'Alexa.ModeController', instance: 'Wash.Cycle', version: '3',
      properties: { supported: [{ name: 'mode' }], retrievable: true, proactivelyReported: true, nonControllable: true },
      capabilityResources: { friendlyNames: [{ '@type': 'text', value: { text: 'Ciclo', locale: 'it-IT' } }] },
      configuration: { ordered: true, supportedModes: [
        { value: 'Wash.Cycle.Off', modeResources: { friendlyNames: [{ '@type': 'text', value: { text: 'Spenta', locale: 'it-IT' } }] } },
        { value: 'Wash.Cycle.Running', modeResources: { friendlyNames: [{ '@type': 'text', value: { text: 'In funzione', locale: 'it-IT' } }] } },
        { value: 'Wash.Cycle.Done', modeResources: { friendlyNames: [{ '@type': 'text', value: { text: 'Finita', locale: 'it-IT' } }] } },
      ] },
      semantics: {
        stateMappings: [
          { '@type': 'States', name: 'Alexa.States.Done', value: 'Wash.Cycle.Done' },
        ],
      },
    },
    {
      type: 'AlexaInterface', interface: 'Alexa.ProactiveNotificationSource', version: '3.0', proactivelyReported: true,
      configuration: { notificationConditions: [{
        conditionType: 'PropertyValueChange',
        property: { type: 'AlexaInterface', interface: 'Alexa.ModeController', instance: 'Wash.Cycle', name: 'mode' },
        valueChangeCondition: { comparator: 'StateEquals', value: 'Alexa.States.Done' },
      }] },
    },
    {
      type: 'AlexaInterface', interface: 'Alexa.EndpointHealth', version: '3',
      properties: { supported: [{ name: 'connectivity' }], proactivelyReported: true, retrievable: true },
    },
    { type: 'AlexaInterface', interface: 'Alexa', version: '3' },
  ],
};

async function exchangeGrant(code) {
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    code,
    client_id: PERMISSIONS_CLIENT_ID,
    client_secret: PERMISSIONS_CLIENT_SECRET,
  }).toString();
  try {
    const res = await fetch('https://api.amazon.com/auth/o2/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    });
    const text = await res.text();
    console.log('LWA_EXCHANGE', res.status, text);
    return res.ok;
  } catch (err) {
    console.log('LWA_EXCHANGE_ERROR', String(err));
    return false;
  }
}

export const handler = async (event) => {
  console.log('EVENT', JSON.stringify(event));
  const header = event?.directive?.header ?? {};
  const ns = header.namespace;
  const name = header.name;

  if (ns === 'Alexa.Discovery' && name === 'Discover') {
    return {
      event: {
        header: { namespace: 'Alexa.Discovery', name: 'Discover.Response', payloadVersion: '3', messageId: crypto.randomUUID() },
        payload: { endpoints: [ENDPOINT] },
      },
    };
  }

  if (ns === 'Alexa.Authorization' && name === 'AcceptGrant') {
    const code = event.directive.payload?.grant?.code;
    console.log('ACCEPT_GRANT_CODE', code);
    await exchangeGrant(code);
    return {
      event: {
        header: { namespace: 'Alexa.Authorization', name: 'AcceptGrant.Response', payloadVersion: '3', messageId: header.messageId || crypto.randomUUID() },
        payload: {},
      },
    };
  }

  if (ns === 'Alexa' && name === 'ReportState') {
    return {
      event: {
        header: { namespace: 'Alexa', name: 'StateReport', payloadVersion: '3', messageId: header.messageId || crypto.randomUUID(), correlationToken: header.correlationToken },
        payload: {},
        context: {
          properties: [
            { namespace: 'Alexa.ModeController', instance: 'Wash.Cycle', name: 'mode', value: 'Wash.Cycle.Off', timeOfSample: new Date().toISOString(), uncertaintyInMilliseconds: 0 },
            { namespace: 'Alexa.EndpointHealth', name: 'connectivity', value: { state: 'OK' }, timeOfSample: new Date().toISOString(), uncertaintyInMilliseconds: 0 },
          ],
        },
        endpoint: { scope: event.directive.endpoint?.scope, endpointId: event.directive.endpoint?.endpointId },
      },
    };
  }

  return {
    event: {
      header: { namespace: ns || 'Alexa', name: 'ErrorResponse', messageId: crypto.randomUUID(), payloadVersion: '3' },
      payload: { type: 'INVALID_DIRECTIVE' },
    },
  };
};
