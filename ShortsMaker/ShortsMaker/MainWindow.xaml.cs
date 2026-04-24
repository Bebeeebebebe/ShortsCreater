using System.Text;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media.Imaging;
using Microsoft.Win32;
using System.IO;
using Microsoft.WindowsAPICodePack.Dialogs;
using System.Linq;
using System.Diagnostics;
using System.Windows.Media;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Globalization;
using System.Windows.Data;
using System.Windows.Input;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Windows.Threading;
using System.Windows.Media.Animation;
using System.Net.Http;
using System.Net.Http.Json;


namespace ShortsMaker
{

    public partial class MainWindow : Window
    {



        private void Log(string message)
        {
            string logPath = Path.Combine(Path.GetTempPath(), "log.txt");
            File.AppendAllText(logPath, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} - {message}{Environment.NewLine}");
        }

        public class VideoFormatEntry
        {
            public string AspectRatio { get; set; }      // 16:9, 9:16, 4:5, ...
            public List<string> VideoPaths { get; set; } = new();
        }


        private DispatcherTimer _previewTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromMilliseconds(300)
        };
        private DirectoryInfo _directory;
        private Dictionary<string, VideoFormatEntry> _videoList = new();
        private VideoFormatEntry? _selectedFormat;
        private string? _selectedSingleVideoPath;
        public ObservableCollection<SubtitleSection> SubtitleSections { get; }
        = new ObservableCollection<SubtitleSection>();

        public ObservableCollection<ImageSection> ImageSections { get; }
            = new ObservableCollection<ImageSection>();

        public ObservableCollection<UploadResourceSection> UploadResourceSections { get; }
    = new ObservableCollection<UploadResourceSection>();
        public ObservableCollection<string> UploadVideos { get; }
    = new ObservableCollection<string>();

        public ObservableCollection<UploadAccountStyle> UploadAccounts { get; }
    = new ObservableCollection<UploadAccountStyle>();

        public MainWindow()
        {
            InitializeComponent();
            DataContext = this;
            _previewTimer = new DispatcherTimer
            {
                Interval = TimeSpan.FromMilliseconds(300)
            };
            _previewTimer.Tick += (_, __) =>
            {
                _previewTimer.Stop();

                var path = GetPreviewVideoPath();
                if (path != null)
                    UpdateVideoPreview(path);
            };

        }
        //Меню
        private const double HiddenMenuOffset = -260;
        private void MenuTrigger_MouseEnter(object sender, MouseEventArgs e)
        {
            ShowMenu(true);
        }

        private void ShowMenu(bool show)
        {
            var anim = new ThicknessAnimation
            {
                To = show
                    ? new Thickness(0, 0, 0, 0)
                    : new Thickness(HiddenMenuOffset, 0, 0, 0),

                Duration = TimeSpan.FromMilliseconds(200),
                DecelerationRatio = 0.8
            };

            SideMenu.BeginAnimation(MarginProperty, anim);
        }

        private void SideMenu_MouseLeave(object sender, MouseEventArgs e)
        {
            ShowMenu(false);
        }

        private void EditorBtn_Click(object sender, RoutedEventArgs e)
        {
            ShowScreen(EditorScreen);
            Highlight(EditorBtn);
        }

        private void CreateBtn_Click(object sender, RoutedEventArgs e)
        {
            ShowScreen(CreateScreen);
            Highlight(CreateBtn);
        }

        private void SendBtn_Click(object sender, RoutedEventArgs e)
        {
            ShowScreen(UploadScreen);
            Highlight(SendBtn);
        }

        private void ShowScreen(UIElement screen)
        {
            EditorScreen.Visibility = Visibility.Collapsed;
            CreateScreen.Visibility = Visibility.Collapsed;
            UploadScreen.Visibility = Visibility.Collapsed;

            screen.Visibility = Visibility.Visible;
        }

        private void Highlight(Button active)
        {
            EditorBtn.Background = Brushes.Transparent;
            CreateBtn.Background = Brushes.Transparent;
            SendBtn.Background = Brushes.Transparent;

            active.Background = new SolidColorBrush(Color.FromArgb(80, 255, 255, 255));
        }

        private void Exit_Click(object sender, RoutedEventArgs e)
        {
            Close();
        }

        //Создание видео

        private void ChooseCreateVideo_Click(object sender, RoutedEventArgs e)
        {
            var dialog = new CommonOpenFileDialog
            {
                Title = "Выберите видео файл"
            };

            dialog.Filters.Add(
                new CommonFileDialogFilter(
                    "Видео файлы", "*.mp4;*.avi;*.mkv;*.mov;*.wmv"));

            if (dialog.ShowDialog() == CommonFileDialogResult.Ok)
            {
                VideoPathBox.Text = dialog.FileName;
            }
        }

        private void ChooseOutputDir_Click(object sender, RoutedEventArgs e)
        {
            var dialog = new CommonOpenFileDialog
            {
                Title = "Выберите папку вывода",
                IsFolderPicker = true
            };

            if (dialog.ShowDialog() == CommonFileDialogResult.Ok)
            {
                OutputDirBox.Text = dialog.FileName;
            }
        }

        private static readonly HttpClient httpClient = new HttpClient
        {
            BaseAddress = new Uri("http://localhost:8000")
        };


        async private void ApplyCreate_Click(object sender, RoutedEventArgs e)
        {
            var mode = (ShortsModeBox.SelectedItem as ComboBoxItem)?.Content?.ToString()
                       ?? "SimpleIntervalShorts";

            bool isSimple = mode == "SimpleIntervalShorts";

            var request = new
            {
                video_path = VideoPathBox.Text,
                output_dir = OutputDirBox.Text,
                clip_mode = (ClipModeBox.SelectedItem as ComboBoxItem)?.Content?.ToString(),
                mode = mode,
                max_workers = int.Parse(WorkersBox.Text),
                // Поля для SimpleIntervalShorts
                interval = isSimple
                    ? double.Parse(IntervalBox.Text, CultureInfo.InvariantCulture)
                    : (double?)null,

                // Поля для TranscribeBasedShorts
                whisper_model = !isSimple
                    ? (WhisperModelBox.SelectedItem as ComboBoxItem)?.Content?.ToString()
                    : null,
                whisper_language = !isSimple
                    ? (WhisperLanguageBox.SelectedItem as ComboBoxItem)?.Content?.ToString()
                    : null,
                min_duration = !isSimple
                    ? double.Parse(MinDurationBox.Text, CultureInfo.InvariantCulture)
                    : (double?)null,
                max_duration = !isSimple
                    ? double.Parse(MaxDurationBox.Text, CultureInfo.InvariantCulture)
                    : (double?)null,
            };

            try
            {
                var createResponse = await httpClient.PostAsJsonAsync("/CreateShortsCreater/", request);
                if (!createResponse.IsSuccessStatusCode) { MessageBox.Show("Ошибка создания объекта"); return; }

                var runResponse = await httpClient.PostAsync("/CreateShorts/", null);
                if (!runResponse.IsSuccessStatusCode) { MessageBox.Show("Ошибка запуска обработки"); return; }

                MessageBox.Show("Создание видео запущено", "Успех", MessageBoxButton.OK, MessageBoxImage.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message, "Ошибка");
            }
        }

        //Левая панель
        private readonly string[] VideoExtensions =
        {
            ".mp4", ".avi", ".mkv", ".mov", ".wmv"
        };

        private void BuildTreeFromFile(FileInfo file)
        {
            if (!VideoExtensions.Contains(file.Extension.ToLower()))
            {
                MessageBox.Show("Выбранный файл не является видео", "Ошибка");
                return;
            }

            TreeViewItem fileNode = CreateFileNode(file);
            VideoTreeView.Items.Add(fileNode);
        }

        private TreeViewItem CreateDirectoryNode(DirectoryInfo directory)
        {

            var subDirs = directory.GetDirectories()
                .Select(CreateDirectoryNode)
                .Where(d => d != null)
                .ToList();

            var videoFiles = directory.GetFiles()
                .Where(f => VideoExtensions.Contains(f.Extension.ToLower()))
                .Select(CreateFileNode)
                .ToList();

            if (!subDirs.Any() && !videoFiles.Any())
            {
                return null; // Папка без видео пропускается
            }

            TreeViewItem dirNode = new TreeViewItem
            {
                Header = CreateHeaderWithIcon(directory.Name, "images/folder_icon.png"),
                Tag = directory.FullName
            };

            foreach (var dir in subDirs)
                dirNode.Items.Add(dir);

            foreach (var file in videoFiles)
                dirNode.Items.Add(file);

            return dirNode;
        }

        private TreeViewItem CreateFileNode(FileInfo file)
        {
            TreeViewItem fileNode = new TreeViewItem
            {
                Header = CreateHeaderWithIcon(file.Name, "images/video_icon.png"),
                Tag = file.FullName
            };
            return fileNode;
        }
        private BitmapImage LoadIcon(string path, int width, int height)
        {
            try
            {
                var icon = new BitmapImage();
                icon.BeginInit();
                icon.UriSource = new Uri($"pack://application:,,,/{path}");
                icon.DecodePixelWidth = width;
                icon.DecodePixelHeight = height;
                icon.EndInit();
                return icon;
            }
            catch
            {
                return null;
            }
        }
        private StackPanel CreateHeaderWithIcon(string text, string iconPath)
        {
            StackPanel stack = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                VerticalAlignment = VerticalAlignment.Center
            };

            BitmapImage icon = LoadIcon(iconPath, 32, 0);

            if (icon != null)
            {
                stack.Children.Add(new Image
                {
                    Source = icon,
                    Width = 32,
                    Height = 32,
                    Stretch = System.Windows.Media.Stretch.Uniform,
                    Margin = new Thickness(0, 0, 6, 0),
                    VerticalAlignment = VerticalAlignment.Center
                });
            }

            stack.Children.Add(new TextBlock
            {
                Text = text,
                FontSize = 20,
                Foreground = System.Windows.Media.Brushes.Black,
                VerticalAlignment = VerticalAlignment.Center
            });

            return stack;
        }

        private void BuildTreeFromDirectory(DirectoryInfo directory)
        {
            TreeViewItem root = CreateDirectoryNode(directory);
            if (root != null)
                VideoTreeView.Items.Add(root);

            _directory = directory;
        }

        private void ChooseFolderButton_Click(object sender, RoutedEventArgs e)
        {
            var dialog = new CommonOpenFileDialog
            {
                Title = "Выберите папку с видео",
                IsFolderPicker = true
            };

            if (dialog.ShowDialog() == CommonFileDialogResult.Ok)
            {
                VideoTreeView.Items.Clear();
                BuildTreeFromDirectory(new DirectoryInfo(dialog.FileName));

                _directory = new DirectoryInfo(dialog.FileName);

                VideoTreeView.Items.Clear();
                BuildTreeFromDirectory(_directory);

                BuildFormatsTree(_directory);
            }

        }

        private void ChooseVideoButton_Click(object sender, RoutedEventArgs e)
        {
            var dialog = new CommonOpenFileDialog
            {
                Title = "Выберите видео файл"
            };

            dialog.Filters.Add(
                new CommonFileDialogFilter(
                    "Видео файлы", "*.mp4;*.avi;*.mkv;*.mov;*.wmv"));

            if (dialog.ShowDialog() == CommonFileDialogResult.Ok)
            {
                VideoTreeView.Items.Clear();
                BuildTreeFromFile(new FileInfo(dialog.FileName));
            }

        }

        //==========================
        //верхняя чать левой панели + визуализация на правой
        //=========================
        private string GetOrientation(int width, int height)
        {
            if (width > height)
                return "Горизонтальные";

            if (height > width)
                return "Вертикальные";

            return "Квадратные";
        }

        private int Gcd(int a, int b)
        {
            while (b != 0)
            {
                int temp = b;
                b = a % b;
                a = temp;
            }
            return a;
        }

        private string GetAspectRatioGroup(int width, int height)
        {
            double ratio = (double)width / height;

            // Популярные форматы (можно расширять)
            var knownRatios = new Dictionary<string, double>
            {
                { "16:9", 16d / 9 },
                { "21:9", 21d / 9 },
                { "4:3", 4d / 3 },
                { "3:4", 3d / 4 },
                { "9:16", 9d / 16 },
                { "4:5", 4d / 5 },
                { "5:4", 5d / 4 },
                { "1:1", 1d }
            };

            const double tolerance = 0.02; // 2%

            foreach (var kv in knownRatios)
            {
                if (Math.Abs(ratio - kv.Value) < tolerance)
                    return kv.Key;
            }

            // fallback — реальный математический формат
            int gcd = Gcd(width, height);
            return $"{width / gcd}:{height / gcd}";
        }

        private (int w, int h)? GetVideoResolution(string path)
        {
            try
            {
                var process = new Process
                {
                    StartInfo = new ProcessStartInfo
                    {
                        FileName = "ffprobe",
                        Arguments = $"-v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 \"{path}\"",
                        RedirectStandardOutput = true,
                        UseShellExecute = false,
                        CreateNoWindow = true
                    }
                };

                process.Start();
                string line = process.StandardOutput.ReadLine();
                process.WaitForExit();

                if (string.IsNullOrWhiteSpace(line))
                    return null;

                var parts = line.Split(',');
                return (int.Parse(parts[0]), int.Parse(parts[1]));
            }
            catch
            {
                return null;
            }
        }

        private void BuildFormatsTree(DirectoryInfo directory)
        {
            FormatsTreeView.Items.Clear();
            _videoList.Clear();

            foreach (var file in directory.GetFiles("*.*", SearchOption.AllDirectories)
                                          .Where(f => VideoExtensions.Contains(f.Extension.ToLower())))
            {
                var res = GetVideoResolution(file.FullName);
                if (res == null) continue;

                string aspect = GetAspectRatioGroup(res.Value.w, res.Value.h);

                if (!_videoList.TryGetValue(aspect, out var entry))
                {
                    entry = new VideoFormatEntry
                    {
                        AspectRatio = aspect
                    };
                    _videoList[aspect] = entry;
                }

                entry.VideoPaths.Add(file.FullName);
            }

            BuildFormatsTreeUI();
        }

        private void BuildFormatsTreeUI()
        {
            var grouped = _videoList
                .GroupBy(v => GetOrientationFromAspect(v.Key))
                .OrderBy(g => g.Key);

            foreach (var orientationGroup in grouped)
            {
                var orientationNode = new TreeViewItem
                {
                    Header = $"{orientationGroup.Key} ({orientationGroup.Sum(g => g.Value.VideoPaths.Count)})",
                    IsExpanded = true
                };

                foreach (var format in orientationGroup.OrderByDescending(f => f.Value.VideoPaths.Count))
                {
                    var formatNode = new TreeViewItem
                    {
                        Header = $"{format.Key} ({format.Value.VideoPaths.Count})",
                        Tag = format.Value,
                        IsExpanded = false
                    };

                    foreach (var path in format.Value.VideoPaths)
                    {
                        formatNode.Items.Add(new TreeViewItem
                        {
                            Header = Path.GetFileName(path),
                            Tag = path
                        });
                    }

                    orientationNode.Items.Add(formatNode);
                }

                FormatsTreeView.Items.Add(orientationNode);
            }
        }


        private string GetOrientationFromAspect(string aspect)
        {
            var parts = aspect.Split(':');
            int w = int.Parse(parts[0]);
            int h = int.Parse(parts[1]);

            if (w > h) return "Горизонтальные";
            if (h > w) return "Вертикальные";
            return "Квадратные";
        }

        private void FormatsTreeView_SelectedItemChanged(object sender, RoutedPropertyChangedEventArgs<object> e)
        {
            if (e.NewValue is not TreeViewItem selectedItem)
                return;

            ResetTreeBackground(FormatsTreeView.Items);

            _selectedFormat = null;
            _selectedSingleVideoPath = null;

            // 1️⃣ Выбран ФОРМАТ
            if (selectedItem.Tag is VideoFormatEntry format)
            {
                _selectedFormat = format;
                HighlightTreeItem(selectedItem, Color.FromRgb(255, 192, 203));
                UpdateRightPanel(format.AspectRatio, format.VideoPaths.First());
            }
            // 2️⃣ Выбрано ОДНО ВИДЕО
            else if (selectedItem.Tag is string videoPath)
            {
                var parentFormat = FindParentFormat(selectedItem);
                if (parentFormat == null)
                    return;

                _selectedSingleVideoPath = videoPath;

                HighlightTreeItem(selectedItem, Color.FromRgb(255, 182, 193)); // чуть темнее
                UpdateRightPanel(parentFormat.AspectRatio, videoPath);
            }
        }

        private VideoFormatEntry? FindParentFormat(TreeViewItem videoItem)
        {
            DependencyObject parent = videoItem;
            while (parent != null)
            {
                if (parent is TreeViewItem tvi && tvi.Tag is VideoFormatEntry format)
                    return format;

                parent = VisualTreeHelper.GetParent(parent);
            }
            return null;
        }

        private VideoFormatEntry? GetCurrentSelection()
        {
            if (GetPreviewVideoPath() == null)
            {
                var format = _selectedFormat!;
                return new VideoFormatEntry
                {
                    AspectRatio = format.AspectRatio,
                    VideoPaths = new List<string> { _selectedSingleVideoPath }
                };
            }

            return _selectedFormat;
        }
        private void UpdateRightPanel(string aspect, string videoPath)
        {
            SelectedAspectText.Text = $"Формат: {aspect}";
            SelectedVideoText.Text = $"Видео: {Path.GetFileName(videoPath)}";

            UpdateVideoPreview(videoPath);
        }

        private string? RenderPlainVideoPreview(string videoPath)
        {
            var res = GetVideoResolution(videoPath);
            var durationOpt = GetVideoDuration(videoPath);

            if (res == null || durationOpt == null || durationOpt.Value <= 0)
                return null;

            double previewTime = durationOpt.Value / 2.0;

            string outPng = Path.Combine(
                Path.GetTempPath(),
                $"preview_plain_{Guid.NewGuid():N}.png");

            var p = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = "ffmpeg",
                    Arguments =
                        "-y " +
                        $"-i \"{videoPath}\" " +
                        $"-ss {previewTime.ToString(CultureInfo.InvariantCulture)} " +
                        "-frames:v 1 " +
                        $"\"{outPng}\"",
                    UseShellExecute = false,
                    RedirectStandardError = true,
                    CreateNoWindow = true
                }
            };

            p.Start();
            p.StandardError.ReadToEnd();
            p.WaitForExit();

            return File.Exists(outPng) ? outPng : null;
        }

        private void UpdateVideoPreview(string videoPath)
        {
            try
            {
                string? imagePath = null;

                bool hasOverlays =
    SubtitleSections.Any(s => s.IsEnabled) ||
    ImageSections.Any(i => i.IsEnabled);

                imagePath = hasOverlays
                    ? RenderPreviewWithOverlays(videoPath)
                    : RenderPlainVideoPreview(videoPath);

                if (imagePath == null || !File.Exists(imagePath))
                    return;

                Dispatcher.Invoke(() =>
                {
                    var bmp = new BitmapImage();
                    bmp.BeginInit();
                    bmp.CacheOption = BitmapCacheOption.OnLoad;
                    bmp.CreateOptions = BitmapCreateOptions.IgnoreImageCache;
                    bmp.UriSource = new Uri(imagePath);
                    bmp.EndInit();
                    bmp.Freeze();

                    VideoPreviewImage.Source = null;
                    VideoPreviewImage.Source = bmp;
                });
            }
            catch
            {
                VideoPreviewImage.Source = null;
            }
        }

        // Рекурсивная подсветка
        private void HighlightTreeItem(TreeViewItem item, Color color)
        {
            item.Background = new SolidColorBrush(color);
            foreach (var obj in item.Items)
            {
                if (obj is TreeViewItem child)
                    HighlightTreeItem(child, color);
            }
        }

        // Сброс всех подсветок
        private void ResetTreeBackground(ItemCollection items)
        {
            foreach (var obj in items)
            {
                if (obj is TreeViewItem item)
                {
                    item.Background = Brushes.Transparent;
                    if (item.Items.Count > 0)
                        ResetTreeBackground(item.Items);
                }
            }
        }


        private double? GetVideoDuration(string path)
        {
            try
            {
                var process = new Process
                {
                    StartInfo = new ProcessStartInfo
                    {
                        FileName = "ffprobe",
                        Arguments = $"-v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \"{path}\"",
                        RedirectStandardOutput = true,
                        UseShellExecute = false,
                        CreateNoWindow = true
                    }
                };

                process.Start();
                string output = process.StandardOutput.ReadLine();
                process.WaitForExit();

                if (double.TryParse(output, System.Globalization.NumberStyles.Any,
                    System.Globalization.CultureInfo.InvariantCulture, out double duration))
                {
                    return duration;
                }
            }
            catch { }

            return null;
        }




        //=============================================
        //центральная панель + визуализация на 3ю
        //==============================================
        private void AddSubtitle_Click(object sender, RoutedEventArgs e)
        {
            var section = new SubtitleSection
            {
                Title = $"Субтитры {SubtitleSections.Count + 1}",
                Description = "Настройки субтитров",
                IsEnabled = true
            };

            section.PropertyChanged += (_, e2) =>
            {
                if (e2.PropertyName == nameof(EditableSection.IsEnabled))
                {
                    if (GetPreviewVideoPath() == null)
                        return;

                    _previewTimer.Stop();
                    _previewTimer.Start();
                }
            };

            // ✅ это ОК — сабы
            section.Style.PropertyChanged += SubtitleStyleChanged;

            SubtitleSections.Add(section);

            if (GetPreviewVideoPath() == null)
            {
                _previewTimer.Stop();
                _previewTimer.Start();
            }

        }

        private void AddImage_Click(object sender, RoutedEventArgs e)
        {
            var section = new ImageSection
            {
                Title = $"Изображение {ImageSections.Count + 1}",
                Description = "Картинка, GIF или видео поверх ролика",
                IsEnabled = true
            };


            section.PropertyChanged += (_, e2) =>
            {
                if (e2.PropertyName == nameof(EditableSection.IsEnabled))
                {
                    if (GetPreviewVideoPath() == null)
                        return;

                    _previewTimer.Stop();
                    _previewTimer.Start();
                }
            };

            // 🔥 реакция на Scale / Opacity / Offset и т.д.
            section.Style.PropertyChanged += OverlayStyleChanged;

            ImageSections.Add(section);

            if (GetPreviewVideoPath() == null)
            {
                _previewTimer.Stop();
                _previewTimer.Start();
            }
        }


        private void DeleteSection_Click(object sender, RoutedEventArgs e)
        {
            if (sender is not Button btn)
                return;

            if (btn.DataContext is not EditableSection section)
                return;

            // 🔥 ВАЖНО: определяем тип секции
            switch (section)
            {
                case SubtitleSection subtitle:
                    SubtitleSections.Remove(subtitle);
                    break;

                case ImageSection image:
                    ImageSections.Remove(image);
                    break;

                case UploadResourceSection upload:
                    UploadResourceSections.Remove(upload);
                    break;
            }
        }

        private void Title_RightClick(object sender, MouseButtonEventArgs e)
        {
            if (sender is TextBlock tb && tb.DataContext is EditableSection section)
            {
                section.IsEditing = true;
                e.Handled = true;

                // задержка, чтобы WPF успел показать TextBox
                tb.Dispatcher.InvokeAsync(() =>
                {
                    if (tb.Parent is Grid grid)
                    {
                        foreach (var child in grid.Children)
                        {
                            if (child is TextBox textBox)
                            {
                                textBox.Focus();
                                textBox.SelectAll();
                                break;
                            }
                        }
                    }
                }, System.Windows.Threading.DispatcherPriority.Input);
            }
        }

        private void TitleEdit_LostFocus(object sender, RoutedEventArgs e)
        {
            if (sender is TextBox tb && tb.DataContext is EditableSection section)
            {
                section.IsEditing = false;
            }
        }

        private void TitleEdit_KeyDown(object sender, KeyEventArgs e)
        {
            if (sender is TextBox tb && tb.DataContext is EditableSection section)
            {
                if (e.Key == Key.Enter || e.Key == Key.Escape)
                {
                    section.IsEditing = false;
                }
            }
        }

        //добавление обновление субтитров

        private string BuildPreviewAssCombined(
    List<SubtitleSection> sections,
    int videoW,
    int videoH,
    double videoDurationSeconds)
        {
            var sb = new StringBuilder();

            sb.AppendLine("[Script Info]");
            sb.AppendLine("ScriptType: v4.00+");
            sb.AppendLine($"PlayResX: {videoW}");
            sb.AppendLine($"PlayResY: {videoH}");
            sb.AppendLine("WrapStyle: 2");
            sb.AppendLine("ScaledBorderAndShadow: yes");
            sb.AppendLine();

            sb.AppendLine("[V4+ Styles]");
            sb.AppendLine("Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV");

            int idx = 0;
            foreach (var sec in sections)
            {
                var s = sec.Style;
                sb.AppendLine(
                    $"Style: S{idx},{s.Font},{s.FontSize},{s.PrimaryColorAss},{s.OutlineColorAss},&H00000000," +
                    $"{(s.Bold ? -1 : 0)},{(s.Italic ? -1 : 0)},1,{s.OutlineWidth},{s.ShadowWidth}," +
                    $"{s.Alignment},{s.MarginL},{s.MarginR},{s.MarginV}");
                idx++;
            }

            sb.AppendLine();
            sb.AppendLine("[Events]");
            sb.AppendLine("Format: Layer,Start,End,Style,Text");

            string FormatTime(TimeSpan t) =>
                $"{t.Hours}:{t.Minutes:D2}:{t.Seconds:D2}.{t.Milliseconds / 10:D2}";

            idx = 0;
            foreach (var sec in sections)
            {
                var s = sec.Style;
                string fade =
                    (s.FadeIn > 0 || s.FadeOut > 0)
                        ? $@"{{\fad({s.FadeIn},{s.FadeOut})}}"
                        : "";

                sb.AppendLine(
                    $"Dialogue: 0,{FormatTime(TimeSpan.Zero)}," +
                    $"{FormatTime(TimeSpan.FromSeconds(videoDurationSeconds))}," +
                    $"S{idx},{fade}Пример субтитров {idx + 1}");
                idx++;
            }

            string path = Path.Combine(
                Path.GetTempPath(),
                $"preview_subs_{Guid.NewGuid():N}.ass");

            File.WriteAllText(path, sb.ToString(), new UTF8Encoding(true));
            return path;
        }

        private string BuildPreviewAss(
    SubtitleSection section,
    int videoW,
    int videoH,
    double videoDurationSeconds)
        {
            var s = section.Style;

            TimeSpan start = TimeSpan.Zero;
            TimeSpan end = TimeSpan.FromSeconds(videoDurationSeconds);

            string FormatTime(TimeSpan t) =>
                $"{t.Hours}:{t.Minutes:D2}:{t.Seconds:D2}.{t.Milliseconds / 10:D2}";

            string fadeTag = (s.FadeIn > 0 || s.FadeOut > 0)
                ? $@"{{\fad({s.FadeIn},{s.FadeOut})}}"
                : "";

            string ass = $@"
[Script Info]
ScriptType: v4.00+
PlayResX: {videoW}
PlayResY: {videoH}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV
Style: Default,{s.Font},{s.FontSize},{s.PrimaryColorAss},{s.OutlineColorAss},&H00000000,{(s.Bold ? -1 : 0)},{(s.Italic ? -1 : 0)},1,{s.OutlineWidth},{s.ShadowWidth},{s.Alignment},{s.MarginL},{s.MarginR},{s.MarginV}

[Events]
Format: Layer,Start,End,Style,Text
Dialogue: 0,{FormatTime(start)},{FormatTime(end)},Default,{fadeTag}Пример субтитров
";

            string path = Path.Combine(
                Path.GetTempPath(),
                $"preview_subs_{Guid.NewGuid():N}.ass");

            File.WriteAllText(path, ass, new UTF8Encoding(true));
            return path;
        }

        private string? RenderPreviewWithOverlays(string videoPath)
        {
            Log("[Preview] RenderPreviewWithOverlays called");

            var res = GetVideoResolution(videoPath);
            var durationOpt = GetVideoDuration(videoPath);

            if (res == null || durationOpt == null || durationOpt.Value <= 0)
                return null;

            double previewTime = durationOpt.Value / 2.0;
            double previewMs = previewTime * 1000.0;

            // ---------- SUBTITLES ----------
            string? assPath = null;
            var activeSubtitles = SubtitleSections
            .OfType<SubtitleSection>()
            .Where(s => s.IsEnabled)
            .ToList();

            if (activeSubtitles.Any())
            {
                assPath = BuildPreviewAssCombined(
                    activeSubtitles,
                    res.Value.w,
                    res.Value.h,
                    durationOpt.Value);
            }

            // ---------- INPUTS ----------
            var inputs = new List<string>
    {
        $"-ss {previewTime.ToString(CultureInfo.InvariantCulture)}",
        $"-i \"{videoPath}\""
    };

            var activeImages = ImageSections
                .Where(i => i.IsEnabled)
                .Select(i => i.Style)
                .Where(s =>
                    previewMs >= s.StartMs &&
                    (s.EndMs == 0 || previewMs <= s.EndMs))
                .ToList();

            foreach (var img in activeImages)
                inputs.Add($"-i \"{img.FilePath}\"");

            // ---------- FILTER COMPLEX ----------
            var filters = new List<string>();
            filters.Add("[0:v]setpts=PTS-STARTPTS[v0]");

            int index = 1;

            foreach (var s in activeImages)
            {
                string scaleStr = s.Scale.ToString(CultureInfo.InvariantCulture);

                filters.Add(
                    $"[{index}:v]" +
                    $"scale=trunc(iw*{scaleStr}):trunc(ih*{scaleStr})," +
                    $"format=rgba,colorchannelmixer=aa={s.Opacity.ToString(CultureInfo.InvariantCulture)}" +
                    $"[img{index}]"
                );

                filters.Add(
                    $"[v{index - 1}][img{index}]" +
                    $"overlay=x={ResolveX(s, res.Value.w)}" +
                    $":y={ResolveY(s, res.Value.h)}" +
                    $"[v{index}]"
                );

                index++;
            }

            string finalVideo = $"v{index - 1}";

            if (assPath != null)
            {
                string escapedAss = assPath.Replace("\\", "/").Replace(":", "\\:");
                filters.Add($"[{finalVideo}]subtitles='{escapedAss}'[vout]");
                finalVideo = "vout";
            }

            string filterComplex = string.Join(";", filters);

            // ---------- OUTPUT ----------
            string outPng = Path.Combine(
                Path.GetTempPath(),
                $"preview_{Guid.NewGuid():N}.png");

            var args =
                "-y " +
                string.Join(" ", inputs) + " " +
                $"-filter_complex \"{filterComplex}\" " +
                $"-map \"[{finalVideo}]\" " +
                "-frames:v 1 " +
                $"\"{outPng}\"";

            var p = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = "ffmpeg",
                    Arguments = args,
                    UseShellExecute = false,
                    RedirectStandardError = true,
                    CreateNoWindow = true
                }
            };

            p.Start();
            p.StandardError.ReadToEnd();
            p.WaitForExit();

            return File.Exists(outPng) ? outPng : null;
        }

        private void SubtitleStyleChanged(object sender, PropertyChangedEventArgs e)
        {
            if (GetPreviewVideoPath() == null)
                return;

            _previewTimer.Stop();
            _previewTimer.Start();
        }

        //добавление субтитров
        private string? ChooseOutputFolder()
        {
            var dialog = new CommonOpenFileDialog
            {
                Title = "Выберите папку для результата",
                IsFolderPicker = true
            };

            return dialog.ShowDialog() == CommonFileDialogResult.Ok
                ? dialog.FileName
                : null;
        }


        private List<string> GetSelectedVideos()
        {
            // выбран конкретный файл
            if (GetPreviewVideoPath() == null)
                return new List<string> { _selectedSingleVideoPath };

            // выбран формат (группа)
            if (_selectedFormat != null)
                return _selectedFormat.VideoPaths.ToList();

            return new List<string>();
        }


        private async Task<bool> SendVideoListAsync(List<string> videos)
        {
            var response = await httpClient.PostAsJsonAsync(
                "/UpdateVideoList/",
                new { videos }
            );

            if (!response.IsSuccessStatusCode)
            {
                MessageBox.Show("Ошибка обновления списка видео");
                return false;
            }

            return true;
        }

        private async Task<bool> SendSubtitleStyleAsync(SubtitleStyle s)
        {
            var fields = new Dictionary<string, string>
            {
                ["font"] = s.Font,
                ["fontsize"] = s.FontSize.ToString(),
                ["primary_color"] = s.PrimaryColorAss,
                ["outline_color"] = s.OutlineColorAss,
                ["outline_width"] = s.OutlineWidth.ToString(CultureInfo.InvariantCulture),
                ["shadow_width"] = s.ShadowWidth.ToString(CultureInfo.InvariantCulture),
                ["bold"] = s.Bold.ToString().ToLower(),
                ["italic"] = s.Italic.ToString().ToLower(),
                ["alignment"] = s.Alignment.ToString(),
                ["margin_v"] = s.MarginV.ToString(),
                ["margin_l"] = s.MarginL.ToString(),
                ["margin_r"] = s.MarginR.ToString(),
                ["fade_in"] = s.FadeIn.ToString(),
                ["fade_out"] = s.FadeOut.ToString()
            };

            foreach (var kv in fields)
            {
                string url =
                    $"/ChangeSubtitleStyle/{kv.Key}/{Uri.EscapeDataString(kv.Value)}";

                var response = await httpClient.PostAsync(url, null);

                if (!response.IsSuccessStatusCode)
                {
                    MessageBox.Show($"Ошибка обновления стиля: {kv.Key}");
                    return false;
                }
            }

            return true;
        }

        private async Task<bool> RunAddSubtitlesAsync(string outputDir)
        {
            var response = await httpClient.PostAsJsonAsync(
                "/AddSubtitles/",
                new
                {
                    output_dir = outputDir,
                    whisper_model = "base",
                    word_timestamps = true
                }
            );

            if (!response.IsSuccessStatusCode)
            {
                MessageBox.Show("Ошибка генерации субтитров");
                return false;
            }

            return true;
        }


        private async void ApplySubtitles_Click(object sender, RoutedEventArgs e)
        {
            // 1️ папка результата
            string? outputDir = ChooseOutputFolder();
            if (outputDir == null)
                return;

            // 2️ видео
            var videos = GetSelectedVideos();
            if (videos.Count == 0)
            {
                MessageBox.Show("Видео не выбраны");
                return;
            }

            // 3️ субтитры
            var subtitleSection = SubtitleSections
                .OfType<SubtitleSection>()
                .FirstOrDefault(s => s.IsEnabled);

            if (subtitleSection == null)
            {
                MessageBox.Show("Субтитры не включены");
                return;
            }

            try
            {
                // 4️ отправка стиля
                if (!await SendSubtitleStyleAsync(subtitleSection.Style))
                    return;

                // 5️ отправка видео листа
                if (!await SendVideoListAsync(videos))
                    return;

                // 6️ генерация
                if (!await RunAddSubtitlesAsync(outputDir))
                    return;

                MessageBox.Show(
                    "Субтитры успешно применены",
                    "Готово",
                    MessageBoxButton.OK,
                    MessageBoxImage.Information
                );
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message, "Ошибка");
            }
        }

        //визуализация картинок
        bool IsVisibleAt(ImageStyle s, double previewMs)
        {
            return previewMs >= s.StartMs &&
                   (s.EndMs == 0 || previewMs <= s.EndMs);
        }

        private void OverlayStyleChanged(object sender, PropertyChangedEventArgs e)
        {
            if (GetPreviewVideoPath() == null)
                return;

            _previewTimer.Stop();
            _previewTimer.Start();
        }

        private int ResolveX(ImageStyle s, int videoW)
        {
            return s.Anchor switch
            {
                Anchor.TopLeft or Anchor.CenterLeft or Anchor.BottomLeft => s.OffsetX,
                Anchor.TopCenter or Anchor.Center or Anchor.BottomCenter =>
                    (videoW / 2) + s.OffsetX,
                Anchor.TopRight or Anchor.CenterRight or Anchor.BottomRight =>
                    videoW + s.OffsetX,
                _ => s.OffsetX
            };
        }

        private int ResolveY(ImageStyle s, int videoH)
        {
            return s.Anchor switch
            {
                Anchor.TopLeft or Anchor.TopCenter or Anchor.TopRight => s.OffsetY,
                Anchor.CenterLeft or Anchor.Center or Anchor.CenterRight =>
                    (videoH / 2) + s.OffsetY,
                Anchor.BottomLeft or Anchor.BottomCenter or Anchor.BottomRight =>
                    videoH + s.OffsetY,
                _ => s.OffsetY
            };
        }

        private string? GetPreviewVideoPath()
        {
            if (_selectedSingleVideoPath != null)
                return _selectedSingleVideoPath;

            if (_selectedFormat != null && _selectedFormat.VideoPaths.Any())
                return _selectedFormat.VideoPaths.First();

            return null;
        }

        //Сбор в ImageDTO
        private List<OverlayDto> BuildOverlayDtos()
        {
            return ImageSections
                .Where(s => s.IsEnabled && !string.IsNullOrEmpty(s.Style.FilePath))
                .Select(s => new OverlayDto
                {
                    file_path = s.Style.FilePath,
                    scale = s.Style.Scale,
                    anchor = s.Style.Anchor switch
                    {
                        Anchor.TopLeft => "top-left",
                        Anchor.TopCenter => "top",
                        Anchor.TopRight => "top-right",
                        Anchor.CenterLeft => "left",
                        Anchor.Center => "center",
                        Anchor.CenterRight => "right",
                        Anchor.BottomLeft => "bottom-left",
                        Anchor.BottomCenter => "bottom",
                        Anchor.BottomRight => "bottom-right",
                        _ => "top-left"
                    },
                    offset_x = s.Style.OffsetX,
                    offset_y = s.Style.OffsetY,
                    opacity = s.Style.Opacity,
                    start_ms = s.Style.StartMs,
                    end_ms = s.Style.EndMs,
                    loop = s.Style.Loop,
                    fade_in = s.Style.FadeIn,
                    fade_out = s.Style.FadeOut
                })
                .ToList();
        }

        //Сбор словаря субтитров
        private Dictionary<string, object> BuildSubtitleStyleDict(SubtitleStyle s)
        {
            return new Dictionary<string, object>
            {
                ["font"] = s.Font,
                ["fontsize"] = s.FontSize,
                ["primary_color"] = s.PrimaryColorAss,
                ["outline_color"] = s.OutlineColorAss,
                ["outline_width"] = s.OutlineWidth,
                ["shadow_width"] = s.ShadowWidth,
                ["bold"] = s.Bold,
                ["italic"] = s.Italic,
                ["alignment"] = s.Alignment,
                ["margin_l"] = s.MarginL,
                ["margin_r"] = s.MarginR,
                ["margin_v"] = s.MarginV,
                ["fade_in"] = s.FadeIn,
                ["fade_out"] = s.FadeOut
            };
        }

        //=========Отправка на сервер==================
        private async Task<bool> SendCompositionAsync(string outputDir)
        {
            var subtitle = SubtitleSections.FirstOrDefault(s => s.IsEnabled);

            var dto = new CompositionDto
            {
                output_dir = outputDir,
                subtitle_style = subtitle != null
        ? BuildSubtitleStyleDict(subtitle.Style)
        : new Dictionary<string, object>(),
                overlays = BuildOverlayDtos(),
                threads = int.TryParse(FfmpegThreadsBox.Text, out var t) ? t : 2  // ← добавить
            };

            var response = await httpClient.PostAsJsonAsync(
                "/UpdateComposition/",
                dto
            );

            if (!response.IsSuccessStatusCode)
            {
                MessageBox.Show("Ошибка отправки композиции");
                return false;
            }

            return true;
        }

        private async Task<bool> RunRenderAsync()
        {
            var response = await httpClient.PostAsync("/RenderComposition/", null);
            return response.IsSuccessStatusCode;
        }

        private async void ApplyComposition_Click(object sender, RoutedEventArgs e)
        {
            var outputDir = ChooseOutputFolder();
            if (outputDir == null) return;

            var videos = GetSelectedVideos();
            // 0️⃣ создание ShortsCreater
            var createResponse = await httpClient.PostAsJsonAsync(
                "/CreateShortsCreater/",
                new
                {
                    video_path = videos.First(),
                    whisper_model = "base",
                    whisper_language = "ru",
                    output_dir = outputDir,
                    clip_mode = "blur",
                    min_duration = 40,
                    max_duration = 120,
                    max_workers = 1
                }
            );

            if (!createResponse.IsSuccessStatusCode)
            {
                MessageBox.Show("Не удалось создать ShortsCreater");
                return;
            }

            // 1️⃣ видео
            if (!await SendVideoListAsync(videos)) return;

            // 2️⃣ композиция
            if (!await SendCompositionAsync(outputDir)) return;

            // 3️⃣ рендер
            if (!await RunRenderAsync()) return;

            MessageBox.Show("Композиция запущена");
        }


        //=========Отправка на сервер==================

        //Загрузка видео

        private void AddUploadVideo_Click(object sender, RoutedEventArgs e)
        {
            var dialog = new Microsoft.Win32.OpenFileDialog
            {
                Filter = "Видео файлы|*.mp4;*.mov;*.avi;*.mkv",
                Multiselect = true
            };

            if (dialog.ShowDialog() == true)
            {
                foreach (var file in dialog.FileNames)
                {
                    UploadVideos.Add(file);
                }
            }
        }
        private void RemoveUploadVideo_Click(object sender, RoutedEventArgs e)
        {
            if (sender is Button button &&
                button.DataContext is string video)
            {
                UploadVideos.Remove(video);
            }
        }

        private void UploadVideoList_KeyDown(object sender, KeyEventArgs e)
        {
            if (e.Key != Key.Delete)
                return;

            if (sender is not ListBox listBox)
                return;

            // Копируем, чтобы не модифицировать коллекцию во время перебора
            var selected = listBox.SelectedItems
                                  .Cast<string>()
                                  .ToList();

            foreach (var video in selected)
            {
                UploadVideos.Remove(video);
            }

            e.Handled = true;
        }

        private void AddResource_Click(object sender, RoutedEventArgs e)
        {
            UploadResourceSections.Add(new UploadResourceSection());
        }

        private void RemoveResource_Click(object sender, RoutedEventArgs e)
        {
            
        }

        private void PickCookies_Click(object sender, RoutedEventArgs e)
        {
            if ((sender as FrameworkElement)?.DataContext is UploadAccountStyle account)
            {
                var dialog = new Microsoft.Win32.OpenFileDialog
                {
                    Filter = "Cookies (*.pkl)|*.pkl"
                };

                if (dialog.ShowDialog() == true)
                    account.CookiesPath = dialog.FileName;
            }
        }

        private void AddGlobalAccount_Click(object sender, RoutedEventArgs e)
        {
            UploadAccounts.Add(new UploadAccountStyle());
        }

        private async void AuthorizeAccount_Click(object sender, RoutedEventArgs e)
        {
            if (sender is Button btn && btn.DataContext is UploadAccountStyle account)
            {
                try
                {
                    btn.IsEnabled = false;
                    btn.Content = "⏳ Запуск...";

                    await account.AuthorizeAsync();

                    btn.Content = "✅ Браузер открыт";
                }
                catch (Exception ex)
                {
                    MessageBox.Show(ex.Message, "Ошибка авторизации");
                    btn.Content = "🔐 Авторизоваться";
                }
                finally
                {
                    btn.IsEnabled = true;
                }
            }
        }

        private static readonly HttpClient _client = new HttpClient
        {
            BaseAddress = new Uri("http://localhost:8000")
        };

        private async Task StartMultiPostAsync(UploadResourceSection section)
        {
            var style = section.Style;

            var selectedAccounts = style.Accounts.Where(a => a.IsSelected).ToList();
            if (!selectedAccounts.Any())
            {
                MessageBox.Show("Не выбраны аккаунты");
                return;
            }

            var requests = new List<MultiPostSingleRequestDto>();

            foreach (var account in selectedAccounts)
            {
                var videosDict = new Dictionary<string, VideoSideTextsDto>();

                foreach (var videoPath in UploadVideos)
                {
                    videosDict[videoPath] = new VideoSideTextsDto
                    {
                        description = style.Description ?? "",
                        hashtags = style.Hashtags ?? "",
                        music_author = style.SoundAuthor ?? "",
                        music_name = style.SoundTitle ?? ""
                    };
                }

                requests.Add(new MultiPostSingleRequestDto
                {
                    platform = style.Platform.ToString(),
                    account_name = account.DisplayName,
                    videos = videosDict
                });
            }

            var dto = new MultiPostRequestDto { requests = requests };
            await _client.PostAsJsonAsync("/StartMultiPost/", dto);
        }

        private async void StartMultiPost_Click(object sender, RoutedEventArgs e)
        {
            if (sender is Button btn &&
                btn.CommandParameter is UploadResourceSection section)
            {
                await StartMultiPostAsync(section);
            }
        }



        private void ShortsModeBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            // Добавить null-проверку
            if (SimplePanel == null || TranscribePanel == null)
                return;

            var selected = (ShortsModeBox.SelectedItem as ComboBoxItem)?.Content?.ToString();
            bool isSimple = selected == "SimpleIntervalShorts";

            SimplePanel.Visibility = isSimple ? Visibility.Visible : Visibility.Collapsed;
            TranscribePanel.Visibility = isSimple ? Visibility.Collapsed : Visibility.Visible;
        }



    }
    public class CompositionDto
    {
        public string output_dir { get; set; }
        public Dictionary<string, object> subtitle_style { get; set; }
        public List<OverlayDto> overlays { get; set; }
        public int threads { get; set; }               // ← новое поле
    }

    public enum SectionType
    {
        Subtitle,
        Image,
        Upload
    }

    public class StringNotEmptyConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            return !string.IsNullOrWhiteSpace(value as string);
        }

        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
        {
            throw new NotImplementedException();
        }
    }
}
