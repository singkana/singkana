import SwiftUI

struct PawprintsOverlayView: View {
    let stamps: [PawprintStamp]
    private let fadeSeconds: TimeInterval = 12

    var body: some View {
        TimelineView(.periodic(from: Date(), by: 0.5)) { context in
            GeometryReader { proxy in
                let size = proxy.size
                ZStack {
                    ForEach(stamps) { stamp in
                        let age = context.date.timeIntervalSince(stamp.createdAt)
                        let t = max(0, min(1, age / fadeSeconds))
                        let visibleOpacity = stamp.opacity * (1 - t)

                        Image(Assets.pawprint)
                            .resizable()
                            .scaledToFit()
                            .frame(width: 34, height: 34)
                            .opacity(visibleOpacity)
                            .position(
                                x: stamp.x * size.width,
                                y: stamp.y * size.height
                            )
                            .allowsHitTesting(false)
                    }
                }
            }
        }
    }
}

