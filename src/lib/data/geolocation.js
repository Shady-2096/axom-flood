const QUICK_POSITION_OPTIONS = {
  enableHighAccuracy: false,
  timeout: 3000,
  maximumAge: 15 * 60 * 1000,
};

const PRECISE_POSITION_OPTIONS = {
  enableHighAccuracy: true,
  timeout: 12000,
  maximumAge: 0,
};

function requestPosition(options) {
  return new Promise((resolve, reject) => {
    if (!globalThis.navigator?.geolocation) {
      reject(new Error("geolocation unavailable"));
      return;
    }
    globalThis.navigator.geolocation.getCurrentPosition(resolve, reject, options);
  });
}

export function geolocationErrorMessage(error) {
  if (error?.code === 1) return "Location permission was not allowed. Enter your village or circle below.";
  if (error?.code === 2) return "Your browser could not find a location. Check that Location is on, or enter your place below.";
  if (error?.code === 3) return "We still could not get your location. Check that Location is on, then try again or enter your place below.";
  return "Location is unavailable in this browser. Enter your place below.";
}

/* Android browsers can miss their first network-position deadline when there
   is no warm location fix. Accept a recent cached position quickly, then make
   one longer GPS-backed attempt before reporting failure. Permission errors
   and unavailable providers are final and must not trigger another prompt. */
export async function getPosition(options = QUICK_POSITION_OPTIONS) {
  try {
    return await requestPosition(options);
  } catch (error) {
    if (error?.code !== 3 || options.enableHighAccuracy) throw error;
    return requestPosition(PRECISE_POSITION_OPTIONS);
  }
}
