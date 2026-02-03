import WidgetKit
import SwiftUI

// MARK: - Entry

struct AirPawsEntry: TimelineEntry {
    let date: Date
    let state: SharedState
    let frameSeed: Int   // 0..2 (thunderは0..1)
}

// MARK: - Provider

struct AirPawsProvider: TimelineProvider {
    func placeholder(in context: Context) -> AirPawsEntry {
        AirPawsEntry(date: Date(), state: SharedStore.shared.load(), frameSeed: 0)
    }

    func getSnapshot(in context: Context, completion: @escaping (AirPawsEntry) -> Void) {
        completion(AirPawsEntry(date: Date(), state: SharedStore.shared.load(), frameSeed: 0))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<AirPawsEntry>) -> Void) {
        let st = SharedStore.shared.load()
        let now = Date()

        // 30分刻みで3エントリ（“動いて見える”）
        let minutes = 30
        let entries: [AirPawsEntry] = (0..<3).map { i in
            let d = Calendar.current.date(byAdding: .minute, value: i * minutes, to: now) ?? now
            return AirPawsEntry(date: d, state: st, frameSeed: i % 3)
        }

        completion(Timeline(entries: entries, policy: .atEnd))
    }
}

// MARK: - Widget Root View

struct AirPawsWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: AirPawsEntry

    var body: some View {
        switch family {
        case .accessoryRectangular:
            lockRectangular(entry)
        default:
            homeSmall(entry)
        }
    }

    // Home: systemSmall
    private func homeSmall(_ entry: AirPawsEntry) -> some View {
        ZStack {
            Image(Assets.bgBase)
                .resizable()
                .scaledToFill()

            Image(Assets.petBase(for: entry.state))
                .resizable()
                .scaledToFit()
                .padding(10)

            if let atm = Assets.atmosphereFrame(for: entry.state.weather, seed: entry.frameSeed) {
                Image(atm)
                    .resizable()
                    .scaledToFill()
                    .opacity(entry.state.lens == .cute ? 1.0 : 0.75)
            }
        }
        .clipped()
        .widgetURL(URL(string: "airpaws://open"))
    }

    // Lock: accessoryRectangular（推奨：猫＋足跡＋空気、情報ほぼ無し）
    private func lockRectangular(_ entry: AirPawsEntry) -> some View {
        ZStack {
            Image(Assets.bgBase)
                .resizable()
                .scaledToFill()

            PawprintsWidgetOverlay(stamps: entry.state.pawprints, lens: entry.state.lens)

            Image(Assets.petBase(for: entry.state))
                .resizable()
                .scaledToFit()
                .padding(.horizontal, 10)
                .padding(.vertical, 6)

            if let atm = Assets.atmosphereFrame(for: entry.state.weather, seed: entry.frameSeed) {
                Image(atm)
                    .resizable()
                    .scaledToFill()
                    .opacity(entry.state.lens == .cute ? 1.0 : 0.75)
            }

            // 名前：ロック画面Rectのみ／任意ON
            if entry.state.showNameOnWidget,
               let name = entry.state.catDisplayName?.trimmingCharacters(in: .whitespacesAndNewlines),
               !name.isEmpty {
                Text(name)
                    .font(.system(size: 12, weight: .regular))
                    .opacity(Assets.nameOpacity(for: entry.state.lens))
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
                    .padding(.trailing, 6)
                    .padding(.bottom, 4)
            }
        }
        .clipped()
        .widgetURL(URL(string: "airpaws://open"))
    }
}

// MARK: - Pawprints Overlay (Widget)

struct PawprintsWidgetOverlay: View {
    let stamps: [PawprintStamp]
    let lens: Lens

    var body: some View {
        // ロック画面は狭いので最新2つだけを“気配”として薄く
        let latest = Array(stamps.suffix(2))
        return GeometryReader { geo in
            ZStack {
                ForEach(latest) { s in
                    Image(Assets.pawprint)
                        .resizable()
                        .scaledToFit()
                        .frame(width: lens == .cute ? 22 : 18, height: lens == .cute ? 22 : 18)
                        .opacity(min(s.opacity, lens == .cute ? 0.45 : 0.28))
                        .position(
                            x: CGFloat(s.x) * geo.size.width,
                            y: CGFloat(s.y) * geo.size.height
                        )
                }
            }
        }
        .allowsHitTesting(false)
    }
}

// MARK: - Widget

@main
struct AirPawsWidget: Widget {
    let kind: String = "AirPawsWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: AirPawsProvider()) { entry in
            AirPawsWidgetView(entry: entry)
        }
        .configurationDisplayName("AirPaws")
        .description("Air that remembers your paws.")
        .supportedFamilies([.systemSmall, .accessoryRectangular])
    }
}

