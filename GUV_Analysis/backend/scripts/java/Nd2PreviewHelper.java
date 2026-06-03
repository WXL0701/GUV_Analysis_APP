import java.awt.Color;
import java.awt.Font;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.File;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Arrays;
import javax.imageio.ImageIO;

import loci.common.DebugTools;
import loci.formats.FormatTools;
import loci.formats.ImageReader;
import ome.units.UNITS;
import ome.units.quantity.Length;
import ome.xml.meta.MetadataRetrieve;
import ome.xml.meta.MetadataStore;

public class Nd2PreviewHelper {
    public static void main(String[] args) throws Exception {
        DebugTools.setRootLevel("ERROR");
        if (args.length < 2) {
            throw new IllegalArgumentException("Usage: metadata|preview ...");
        }
        String command = args[0];
        if ("metadata".equals(command)) {
            writeMetadata(args[1], args[2]);
            return;
        }
        if ("preview".equals(command)) {
            if (args.length < 16) {
                throw new IllegalArgumentException("preview requires 15 arguments");
            }
            renderPreview(
                args[1],
                args[2],
                parseInt(args[3], 0),
                parseInt(args[4], 0),
                parseInt(args[5], 0),
                parseInt(args[6], 1),
                parseInt(args[7], 0),
                args[8],
                args[9],
                args[10],
                args[11],
                args[12],
                args[13],
                parseInt(args[14], 512),
                args[15]
            );
            return;
        }
        if ("videoFrames".equals(command)) {
            if (args.length < 23) {
                throw new IllegalArgumentException("videoFrames requires 22 arguments");
            }
            renderVideoFrames(
                args[1],
                args[2],
                parseInt(args[3], 0),
                parseInt(args[4], 0),
                parseInt(args[5], 0),
                parseInt(args[6], 1),
                parseInt(args[7], 0),
                parseInt(args[8], 0),
                args[9],
                args[10],
                args[11],
                args[12],
                args[13],
                parseInt(args[14], 720),
                parseInt(args[15], 0) == 1,
                parseDouble(args[16], 50),
                parseDouble(args[17], Double.NaN),
                parseInt(args[18], 1) == 1,
                parseInt(args[19], 1),
                parseDouble(args[20], Double.NaN),
                args[21],
                parseInt(args[22], 1) == 1
            );
            return;
        }
        throw new IllegalArgumentException("Unsupported command: " + command);
    }

    private static void writeMetadata(String nd2Path, String outPath) throws Exception {
        ImageReader reader = new ImageReader();
        try {
            reader.setId(nd2Path);
            MetadataStore store = reader.getMetadataStore();
            MetadataRetrieve retrieve = store instanceof MetadataRetrieve ? (MetadataRetrieve) store : null;
            StringBuilder sb = new StringBuilder();
            sb.append("{\"filename\":").append(json(new File(nd2Path).getName())).append(",\"series\":[");
            int count = reader.getSeriesCount();
            for (int s = 0; s < count; s++) {
                if (s > 0) sb.append(",");
                reader.setSeries(s);
                sb.append("{");
                sb.append("\"index\":").append(s).append(",");
                sb.append("\"name\":").append(json("Series " + (s + 1))).append(",");
                sb.append("\"size_x\":").append(reader.getSizeX()).append(",");
                sb.append("\"size_y\":").append(reader.getSizeY()).append(",");
                sb.append("\"size_z\":").append(reader.getSizeZ()).append(",");
                sb.append("\"size_c\":").append(reader.getSizeC()).append(",");
                sb.append("\"size_t\":").append(reader.getSizeT()).append(",");
                Double px = pixelSizeUm(retrieve, s);
                sb.append("\"pixel_size_um\":").append(px == null ? "null" : px).append(",");
                sb.append("\"channels\":[");
                int cCount = reader.getSizeC();
                for (int c = 0; c < cCount; c++) {
                    if (c > 0) sb.append(",");
                    String name = channelName(retrieve, s, c);
                    sb.append("{\"index\":").append(c + 1).append(",\"name\":").append(json(name)).append("}");
                }
                sb.append("]}");
            }
            sb.append("]}");
            java.nio.file.Files.writeString(new File(outPath).toPath(), sb.toString());
        } finally {
            reader.close();
        }
    }

    private static void renderPreview(
        String nd2Path,
        String outPath,
        int series,
        int z,
        int c1,
        int c2,
        int t,
        String mode,
        String lut1,
        String lut2,
        String minValue,
        String maxValue,
        String quality,
        int maxPx,
        String cacheSeed
    ) throws Exception {
        ImageReader reader = new ImageReader();
        try {
            reader.setId(nd2Path);
            int sMax = Math.max(0, reader.getSeriesCount() - 1);
            series = clamp(series, 0, sMax);
            reader.setSeries(series);
            z = clamp(z, 0, Math.max(0, reader.getSizeZ() - 1));
            t = clamp(t, 0, Math.max(0, reader.getSizeT() - 1));
            c1 = clamp(c1, 0, Math.max(0, reader.getSizeC() - 1));
            c2 = clamp(c2, 0, Math.max(0, reader.getSizeC() - 1));

            int w = reader.getSizeX();
            int h = reader.getSizeY();
            boolean fast = "fast".equalsIgnoreCase(quality);
            int[] target = fastTargetSize(w, h, maxPx);
            if (fast && (target[0] != w || target[1] != h)) {
                RawPlane plane1 = readRawPlane(reader, z, c1, t);
                BufferedImage image;
                if ("merge".equalsIgnoreCase(mode) && reader.getSizeC() > 1) {
                    RawPlane plane2 = readRawPlane(reader, z, c2, t);
                    image = renderMergeScaled(plane1, plane2, target[0], target[1], lut1, lut2, minValue, maxValue);
                } else {
                    image = renderSingleScaled(plane1, target[0], target[1], lut1, minValue, maxValue);
                }
                ImageIO.write(image, "png", new File(outPath));
                return;
            }

            double[] plane1 = readPlane(reader, z, c1, t);
            BufferedImage image;
            if ("merge".equalsIgnoreCase(mode) && reader.getSizeC() > 1) {
                double[] plane2 = readPlane(reader, z, c2, t);
                image = renderMerge(plane1, plane2, w, h, lut1, lut2, minValue, maxValue);
            } else {
                image = renderSingle(plane1, w, h, lut1, minValue, maxValue);
            }
            ImageIO.write(image, "png", new File(outPath));
        } finally {
            reader.close();
        }
    }

    private static void renderVideoFrames(
        String nd2Path,
        String outDir,
        int series,
        int z,
        int c1,
        int c2,
        int tStart,
        int tEnd,
        String mode,
        String lut1,
        String lut2,
        String minValue,
        String maxValue,
        int maxPx,
        boolean scaleBarEnable,
        double scaleBarLengthUm,
        double pixelSizeUm,
        boolean timeEnable,
        int startFrame,
        double intervalS,
        String timeUnit,
        boolean showFrameNumber
    ) throws Exception {
        ImageReader reader = new ImageReader();
        try {
            reader.setId(nd2Path);
            series = clamp(series, 0, Math.max(0, reader.getSeriesCount() - 1));
            reader.setSeries(series);
            z = clamp(z, 0, Math.max(0, reader.getSizeZ() - 1));
            c1 = clamp(c1, 0, Math.max(0, reader.getSizeC() - 1));
            c2 = clamp(c2, 0, Math.max(0, reader.getSizeC() - 1));
            tStart = clamp(tStart, 0, Math.max(0, reader.getSizeT() - 1));
            tEnd = clamp(tEnd, tStart, Math.max(0, reader.getSizeT() - 1));
            int[] target = fastTargetSize(reader.getSizeX(), reader.getSizeY(), maxPx);
            File dir = new File(outDir);
            dir.mkdirs();
            for (int t = tStart; t <= tEnd; t++) {
                RawPlane plane1 = readRawPlane(reader, z, c1, t);
                BufferedImage image;
                if ("merge".equalsIgnoreCase(mode) && reader.getSizeC() > 1) {
                    RawPlane plane2 = readRawPlane(reader, z, c2, t);
                    image = renderMergeScaled(plane1, plane2, target[0], target[1], lut1, lut2, minValue, maxValue);
                } else {
                    image = renderSingleScaled(plane1, target[0], target[1], lut1, minValue, maxValue);
                }
                drawVideoOverlays(
                    image,
                    t,
                    tStart,
                    scaleBarEnable,
                    scaleBarLengthUm,
                    pixelSizeUm,
                    timeEnable,
                    startFrame,
                    intervalS,
                    timeUnit,
                    showFrameNumber,
                    (double) target[0] / Math.max(1, reader.getSizeX())
                );
                File out = new File(dir, String.format("frame_%06d.png", (t - tStart) + 1));
                ImageIO.write(image, "png", out);
            }
        } finally {
            reader.close();
        }
    }

    private static void drawVideoOverlays(
        BufferedImage image,
        int t,
        int tStart,
        boolean scaleBarEnable,
        double scaleBarLengthUm,
        double pixelSizeUm,
        boolean timeEnable,
        int startFrame,
        double intervalS,
        String timeUnit,
        boolean showFrameNumber,
        double scale
    ) {
        Graphics2D g = image.createGraphics();
        try {
            g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
            g.setColor(Color.WHITE);
            int fontSize = Math.max(14, Math.round(image.getWidth() / 36.0f));
            g.setFont(new Font(Font.SANS_SERIF, Font.BOLD, fontSize));
            int margin = Math.max(12, Math.round(image.getWidth() / 40.0f));
            if (timeEnable) {
                String label = "";
                int frameNumber = startFrame + (t - tStart);
                if (Double.isFinite(intervalS)) {
                    double seconds = Math.max(0, (frameNumber - startFrame) * intervalS);
                    if ("min".equalsIgnoreCase(timeUnit)) {
                        label = String.format("t = %.2f min", seconds / 60.0);
                    } else {
                        label = String.format("t = %.1f s", seconds);
                    }
                    if (showFrameNumber) label += String.format(" | frame %03d", frameNumber);
                } else if (showFrameNumber) {
                    label = String.format("frame %03d", frameNumber);
                }
                if (!label.isBlank()) {
                    drawReadableString(g, label, margin, margin + fontSize, fontSize);
                }
            }
            if (scaleBarEnable && Double.isFinite(pixelSizeUm) && pixelSizeUm > 0 && scaleBarLengthUm > 0) {
                int barW = Math.max(4, (int) Math.round((scaleBarLengthUm / pixelSizeUm) * scale));
                barW = Math.min(barW, image.getWidth() - 2 * margin);
                int barH = Math.max(4, Math.round(fontSize / 5.0f));
                int x = image.getWidth() - margin - barW;
                int y = image.getHeight() - margin - barH;
                g.setColor(Color.BLACK);
                g.fillRect(x - 2, y - 2, barW + 4, barH + 4);
                g.setColor(Color.WHITE);
                g.fillRect(x, y, barW, barH);
                String label = String.format("%.0f um", scaleBarLengthUm);
                int textW = g.getFontMetrics().stringWidth(label);
                drawReadableString(g, label, x + Math.max(0, (barW - textW) / 2), y - 6, fontSize);
            }
        } finally {
            g.dispose();
        }
    }

    private static void drawReadableString(Graphics2D g, String text, int x, int y, int fontSize) {
        g.setColor(Color.BLACK);
        g.drawString(text, x + 2, y + 2);
        g.setColor(Color.WHITE);
        g.drawString(text, x, y);
    }

    private static RawPlane readRawPlane(ImageReader reader, int z, int c, int t) throws Exception {
        byte[] bytes = reader.openBytes(reader.getIndex(z, c, t));
        return new RawPlane(
            bytes,
            reader.getPixelType(),
            FormatTools.getBytesPerPixel(reader.getPixelType()),
            reader.isLittleEndian(),
            reader.getSizeX(),
            reader.getSizeY()
        );
    }

    private static class RawPlane {
        final byte[] bytes;
        final int pixelType;
        final int bpp;
        final int w;
        final int h;
        final ByteBuffer bb;

        RawPlane(byte[] bytes, int pixelType, int bpp, boolean littleEndian, int w, int h) {
            this.bytes = bytes;
            this.pixelType = pixelType;
            this.bpp = bpp;
            this.w = w;
            this.h = h;
            this.bb = ByteBuffer.wrap(bytes).order(littleEndian ? ByteOrder.LITTLE_ENDIAN : ByteOrder.BIG_ENDIAN);
        }

        double valueAtIndex(int i) {
            switch (pixelType) {
                case FormatTools.UINT8:
                    return bytes[i] & 0xff;
                case FormatTools.INT8:
                    return bytes[i];
                case FormatTools.UINT16:
                    return bb.getShort(i * bpp) & 0xffff;
                case FormatTools.INT16:
                    return bb.getShort(i * bpp);
                case FormatTools.UINT32:
                    return bb.getInt(i * bpp) & 0xffffffffL;
                case FormatTools.INT32:
                    return bb.getInt(i * bpp);
                case FormatTools.FLOAT:
                    return bb.getFloat(i * bpp);
                case FormatTools.DOUBLE:
                    return bb.getDouble(i * bpp);
                default:
                    return 0;
            }
        }
    }

    private static double[] readPlane(ImageReader reader, int z, int c, int t) throws Exception {
        byte[] bytes = reader.openBytes(reader.getIndex(z, c, t));
        int pixelType = reader.getPixelType();
        int bpp = FormatTools.getBytesPerPixel(pixelType);
        int n = reader.getSizeX() * reader.getSizeY();
        double[] out = new double[n];
        ByteBuffer bb = ByteBuffer.wrap(bytes).order(reader.isLittleEndian() ? ByteOrder.LITTLE_ENDIAN : ByteOrder.BIG_ENDIAN);
        for (int i = 0; i < n; i++) {
            switch (pixelType) {
                case FormatTools.UINT8:
                    out[i] = bytes[i] & 0xff;
                    break;
                case FormatTools.INT8:
                    out[i] = bytes[i];
                    break;
                case FormatTools.UINT16:
                    out[i] = bb.getShort(i * bpp) & 0xffff;
                    break;
                case FormatTools.INT16:
                    out[i] = bb.getShort(i * bpp);
                    break;
                case FormatTools.UINT32:
                    out[i] = bb.getInt(i * bpp) & 0xffffffffL;
                    break;
                case FormatTools.INT32:
                    out[i] = bb.getInt(i * bpp);
                    break;
                case FormatTools.FLOAT:
                    out[i] = bb.getFloat(i * bpp);
                    break;
                case FormatTools.DOUBLE:
                    out[i] = bb.getDouble(i * bpp);
                    break;
                default:
                    out[i] = 0;
            }
        }
        return out;
    }

    private static BufferedImage renderSingle(double[] plane, int w, int h, String lut, String minValue, String maxValue) {
        double[] range = range(plane, minValue, maxValue, false);
        BufferedImage img = new BufferedImage(w, h, BufferedImage.TYPE_INT_RGB);
        for (int i = 0; i < plane.length; i++) {
            int gray = normalize(plane[i], range[0], range[1]);
            img.setRGB(i % w, i / w, applyLut(gray, lut));
        }
        return img;
    }

    private static BufferedImage renderMerge(double[] p1, double[] p2, int w, int h, String lut1, String lut2, String minValue, String maxValue) {
        double[] r1 = range(p1, minValue, maxValue, false);
        double[] r2 = range(p2, minValue, maxValue, false);
        BufferedImage img = new BufferedImage(w, h, BufferedImage.TYPE_INT_RGB);
        for (int i = 0; i < p1.length; i++) {
            int rgb1 = applyLut(normalize(p1[i], r1[0], r1[1]), lut1);
            int rgb2 = applyLut(normalize(p2[i], r2[0], r2[1]), lut2);
            int r = Math.min(255, ((rgb1 >> 16) & 255) + ((rgb2 >> 16) & 255));
            int g = Math.min(255, ((rgb1 >> 8) & 255) + ((rgb2 >> 8) & 255));
            int b = Math.min(255, (rgb1 & 255) + (rgb2 & 255));
            img.setRGB(i % w, i / w, (r << 16) | (g << 8) | b);
        }
        return img;
    }

    private static BufferedImage renderSingleScaled(double[] plane, int w, int h, int tw, int th, String lut, String minValue, String maxValue) {
        double[] range = range(plane, minValue, maxValue, true);
        BufferedImage img = new BufferedImage(tw, th, BufferedImage.TYPE_INT_RGB);
        double sx = (double) w / tw;
        double sy = (double) h / th;
        for (int y = 0; y < th; y++) {
            double srcY = (y + 0.5) * sy - 0.5;
            for (int x = 0; x < tw; x++) {
                double srcX = (x + 0.5) * sx - 0.5;
                int gray = normalize(sampleBilinear(plane, w, h, srcX, srcY), range[0], range[1]);
                img.setRGB(x, y, applyLut(gray, lut));
            }
        }
        return img;
    }

    private static BufferedImage renderSingleScaled(RawPlane plane, int tw, int th, String lut, String minValue, String maxValue) {
        double[] range = range(plane, minValue, maxValue);
        BufferedImage img = new BufferedImage(tw, th, BufferedImage.TYPE_INT_RGB);
        double sx = (double) plane.w / tw;
        double sy = (double) plane.h / th;
        for (int y = 0; y < th; y++) {
            double srcY = (y + 0.5) * sy - 0.5;
            for (int x = 0; x < tw; x++) {
                double srcX = (x + 0.5) * sx - 0.5;
                int gray = normalize(sampleBilinear(plane, srcX, srcY), range[0], range[1]);
                img.setRGB(x, y, applyLut(gray, lut));
            }
        }
        return img;
    }

    private static BufferedImage renderMergeScaled(double[] p1, double[] p2, int w, int h, int tw, int th, String lut1, String lut2, String minValue, String maxValue) {
        double[] r1 = range(p1, minValue, maxValue, true);
        double[] r2 = range(p2, minValue, maxValue, true);
        BufferedImage img = new BufferedImage(tw, th, BufferedImage.TYPE_INT_RGB);
        double sx = (double) w / tw;
        double sy = (double) h / th;
        for (int y = 0; y < th; y++) {
            double srcY = (y + 0.5) * sy - 0.5;
            for (int x = 0; x < tw; x++) {
                double srcX = (x + 0.5) * sx - 0.5;
                int rgb1 = applyLut(normalize(sampleBilinear(p1, w, h, srcX, srcY), r1[0], r1[1]), lut1);
                int rgb2 = applyLut(normalize(sampleBilinear(p2, w, h, srcX, srcY), r2[0], r2[1]), lut2);
                int r = Math.min(255, ((rgb1 >> 16) & 255) + ((rgb2 >> 16) & 255));
                int g = Math.min(255, ((rgb1 >> 8) & 255) + ((rgb2 >> 8) & 255));
                int b = Math.min(255, (rgb1 & 255) + (rgb2 & 255));
                img.setRGB(x, y, (r << 16) | (g << 8) | b);
            }
        }
        return img;
    }

    private static BufferedImage renderMergeScaled(RawPlane p1, RawPlane p2, int tw, int th, String lut1, String lut2, String minValue, String maxValue) {
        double[] r1 = range(p1, minValue, maxValue);
        double[] r2 = range(p2, minValue, maxValue);
        BufferedImage img = new BufferedImage(tw, th, BufferedImage.TYPE_INT_RGB);
        double sx = (double) p1.w / tw;
        double sy = (double) p1.h / th;
        for (int y = 0; y < th; y++) {
            double srcY = (y + 0.5) * sy - 0.5;
            for (int x = 0; x < tw; x++) {
                double srcX = (x + 0.5) * sx - 0.5;
                int rgb1 = applyLut(normalize(sampleBilinear(p1, srcX, srcY), r1[0], r1[1]), lut1);
                int rgb2 = applyLut(normalize(sampleBilinear(p2, srcX, srcY), r2[0], r2[1]), lut2);
                int r = Math.min(255, ((rgb1 >> 16) & 255) + ((rgb2 >> 16) & 255));
                int g = Math.min(255, ((rgb1 >> 8) & 255) + ((rgb2 >> 8) & 255));
                int b = Math.min(255, (rgb1 & 255) + (rgb2 & 255));
                img.setRGB(x, y, (r << 16) | (g << 8) | b);
            }
        }
        return img;
    }

    private static int[] fastTargetSize(int w, int h, int maxPx) {
        if (maxPx <= 0) maxPx = 512;
        int longest = Math.max(w, h);
        if (longest <= maxPx) return new int[] {w, h};
        double scale = (double) maxPx / longest;
        return new int[] {
            Math.max(1, (int) Math.round(w * scale)),
            Math.max(1, (int) Math.round(h * scale)),
        };
    }

    private static double sampleBilinear(double[] plane, int w, int h, double x, double y) {
        if (x < 0) x = 0;
        if (y < 0) y = 0;
        if (x > w - 1) x = w - 1;
        if (y > h - 1) y = h - 1;
        int x0 = (int) Math.floor(x);
        int y0 = (int) Math.floor(y);
        int x1 = Math.min(w - 1, x0 + 1);
        int y1 = Math.min(h - 1, y0 + 1);
        double fx = x - x0;
        double fy = y - y0;
        double v00 = plane[y0 * w + x0];
        double v10 = plane[y0 * w + x1];
        double v01 = plane[y1 * w + x0];
        double v11 = plane[y1 * w + x1];
        double v0 = v00 + (v10 - v00) * fx;
        double v1 = v01 + (v11 - v01) * fx;
        return v0 + (v1 - v0) * fy;
    }

    private static double sampleBilinear(RawPlane plane, double x, double y) {
        if (x < 0) x = 0;
        if (y < 0) y = 0;
        if (x > plane.w - 1) x = plane.w - 1;
        if (y > plane.h - 1) y = plane.h - 1;
        int x0 = (int) Math.floor(x);
        int y0 = (int) Math.floor(y);
        int x1 = Math.min(plane.w - 1, x0 + 1);
        int y1 = Math.min(plane.h - 1, y0 + 1);
        double fx = x - x0;
        double fy = y - y0;
        double v00 = plane.valueAtIndex(y0 * plane.w + x0);
        double v10 = plane.valueAtIndex(y0 * plane.w + x1);
        double v01 = plane.valueAtIndex(y1 * plane.w + x0);
        double v11 = plane.valueAtIndex(y1 * plane.w + x1);
        double v0 = v00 + (v10 - v00) * fx;
        double v1 = v01 + (v11 - v01) * fx;
        return v0 + (v1 - v0) * fy;
    }

    private static double[] range(double[] plane, String minValue, String maxValue, boolean sampled) {
        double lo = parseDouble(minValue, Double.NaN);
        double hi = parseDouble(maxValue, Double.NaN);
        if (!Double.isFinite(lo) || !Double.isFinite(hi) || hi <= lo) {
            double[] copy = sampled ? sampleForRange(plane) : plane.clone();
            Arrays.sort(copy);
            lo = copy[Math.max(0, Math.min(copy.length - 1, (int) Math.floor((copy.length - 1) * 0.01)))];
            hi = copy[Math.max(0, Math.min(copy.length - 1, (int) Math.floor((copy.length - 1) * 0.99)))];
        }
        if (!Double.isFinite(lo)) lo = 0;
        if (!Double.isFinite(hi) || hi <= lo) hi = lo + 1;
        return new double[] {lo, hi};
    }

    private static double[] range(RawPlane plane, String minValue, String maxValue) {
        double lo = parseDouble(minValue, Double.NaN);
        double hi = parseDouble(maxValue, Double.NaN);
        if (!Double.isFinite(lo) || !Double.isFinite(hi) || hi <= lo) {
            double[] copy = sampleForRange(plane);
            Arrays.sort(copy);
            lo = copy[Math.max(0, Math.min(copy.length - 1, (int) Math.floor((copy.length - 1) * 0.01)))];
            hi = copy[Math.max(0, Math.min(copy.length - 1, (int) Math.floor((copy.length - 1) * 0.99)))];
        }
        if (!Double.isFinite(lo)) lo = 0;
        if (!Double.isFinite(hi) || hi <= lo) hi = lo + 1;
        return new double[] {lo, hi};
    }

    private static double[] sampleForRange(double[] plane) {
        int limit = Math.min(65536, plane.length);
        double[] out = new double[limit];
        double step = (double) plane.length / limit;
        for (int i = 0; i < limit; i++) {
            out[i] = plane[Math.min(plane.length - 1, (int) Math.floor(i * step))];
        }
        return out;
    }

    private static double[] sampleForRange(RawPlane plane) {
        int n = plane.w * plane.h;
        int limit = Math.min(65536, n);
        double[] out = new double[limit];
        double step = (double) n / limit;
        for (int i = 0; i < limit; i++) {
            out[i] = plane.valueAtIndex(Math.min(n - 1, (int) Math.floor(i * step)));
        }
        return out;
    }

    private static int normalize(double value, double lo, double hi) {
        int v = (int) Math.round(255.0 * (value - lo) / (hi - lo));
        return clamp(v, 0, 255);
    }

    private static int applyLut(int gray, String lut) {
        String l = lut == null ? "gray" : lut.toLowerCase();
        int r = gray, g = gray, b = gray;
        if ("green".equals(l)) { r = 0; b = 0; }
        else if ("red".equals(l)) { g = 0; b = 0; }
        else if ("magenta".equals(l)) { g = 0; }
        else if ("cyan".equals(l)) { r = 0; }
        return (r << 16) | (g << 8) | b;
    }

    private static Double pixelSizeUm(MetadataRetrieve store, int series) {
        if (store == null) return null;
        try {
            Length len = store.getPixelsPhysicalSizeX(series);
            if (len == null) return null;
            return len.value(UNITS.MICROMETER).doubleValue();
        } catch (Exception e) {
            return null;
        }
    }

    private static String channelName(MetadataRetrieve store, int series, int channel) {
        if (store == null) return String.format("C%02d", channel + 1);
        try {
            String name = store.getChannelName(series, channel);
            if (name != null && !name.isBlank()) return name;
        } catch (Exception e) {
        }
        return String.format("C%02d", channel + 1);
    }

    private static int parseInt(String value, int fallback) {
        try { return Integer.parseInt(value); } catch (Exception e) { return fallback; }
    }

    private static double parseDouble(String value, double fallback) {
        if (value == null || value.isBlank() || "auto".equalsIgnoreCase(value)) return fallback;
        try { return Double.parseDouble(value); } catch (Exception e) { return fallback; }
    }

    private static int clamp(int value, int lo, int hi) {
        return Math.max(lo, Math.min(hi, value));
    }

    private static String json(String value) {
        if (value == null) return "null";
        return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }
}
