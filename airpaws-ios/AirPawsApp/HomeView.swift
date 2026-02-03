import SwiftUI
import WidgetKit

struct HomeView: View {
    @State private var state: SharedState = SharedStore.shared.load()
    @State private var isBlinking = false

    var body: some View {
        ZStack {
            Image(Assets.bgBase)
                .resizable()
                .scaledToFill()
                .ignoresSafeArea()

            GeometryReader { proxy in
                let size = proxy.size

                ZStack {
                    // 猫
                    Image(isBlinking ? Assets.petBlink(for: state) : Assets.petBase(for: state))
                        .resizable()
                        .scaledToFit()
                        .frame(width: min(size.width * 0.78, 420))
                        .shadow(color: .black.opacity(0.08), radius: 14, x: 0, y: 8)
                        .contentShape(Rectangle())

                    // 足跡（表示のみ：12秒フェードアウト）
                    PawprintsOverlayView(stamps: state.pawprints)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onEnded { value in
                            handleTap(location: value.location, in: size)
                        }
                )
            }

            VStack {
                Spacer()
                lensBar
                    .padding(.bottom, 18)
            }
        }
        .onAppear {
            state = SharedStore.shared.load()
        }
    }

    private var lensBar: some View {
        HStack(spacing: 10) {
            lensButton(.cute)
            lensButton(.chic)
        }
        .padding(10)
        .background(.ultraThinMaterial, in: Capsule())
        .padding(.horizontal, 18)
        .accessibilityElement(children: .contain)
    }

    private func lensButton(_ lens: Lens) -> some View {
        Button {
            setLens(lens)
        } label: {
            Text(lens == .cute ? "Cute" : "Chic")
                .font(.system(size: 14, weight: .semibold))
                .padding(.vertical, 8)
                .padding(.horizontal, 14)
                .background(
                    Capsule()
                        .fill(state.lens == lens ? Color.primary.opacity(0.14) : Color.clear)
                )
        }
        .buttonStyle(.plain)
    }

    private func setLens(_ lens: Lens) {
        state.lens = lens
        SharedStore.shared.update { $0.lens = lens }
        WidgetCenter.shared.reloadAllTimelines()
    }

    private func handleTap(location: CGPoint, in size: CGSize) {
        blink()

        let nx = clamp(location.x / max(size.width, 1), 0, 1)
        let ny = clamp(location.y / max(size.height, 1), 0, 1)

        let stamp = PawprintStamp(x: nx, y: ny, opacity: 0.95, createdAt: Date())
        state.pawprints = ([stamp] + state.pawprints).prefix(AppConstants.maxPawprints).map { $0 }

        SharedStore.shared.update { shared in
            shared.pawprints = ([stamp] + shared.pawprints).prefix(AppConstants.maxPawprints).map { $0 }
        }

        WidgetCenter.shared.reloadAllTimelines()
    }

    private func blink() {
        isBlinking = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.16) {
            isBlinking = false
        }
    }

    private func clamp(_ v: Double, _ minV: Double, _ maxV: Double) -> Double {
        min(max(v, minV), maxV)
    }
}

#Preview {
    HomeView()
}

