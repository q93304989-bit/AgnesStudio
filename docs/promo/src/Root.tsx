import { Composition } from "remotion";
import { AgnesPromo } from "./AgnesPromo";

const FPS = 30;
const DURATION_SECONDS = 30;
const WIDTH = 1920;
const HEIGHT = 1080;

export const Root = () => (
  <>
    <Composition
      id="AgnesPromo"
      component={AgnesPromo}
      durationInFrames={FPS * DURATION_SECONDS}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
  </>
);