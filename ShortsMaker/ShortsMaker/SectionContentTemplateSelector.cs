using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Controls;
using System.Windows;

namespace ShortsMaker
{
    public class SectionContentTemplateSelector : DataTemplateSelector
    {
        public DataTemplate SubtitleTemplate { get; set; }
        public DataTemplate ImageTemplate { get; set; }

        public DataTemplate UploadResourceTemplate { get; set; }

        public override DataTemplate SelectTemplate(object item, DependencyObject container)
        {
            return item switch
            {
                SubtitleSection => SubtitleTemplate,
                ImageSection => ImageTemplate,
                UploadResourceSection => UploadResourceTemplate,
                _ => null
            };
        }
    }
}
