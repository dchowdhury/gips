#include <gip/GeoRaster.h>
#include <gip/GeoImage.h>

#include <gip/GeoRasterIO.h>

using namespace std;

namespace gip {

	// Copy constructor
	GeoRaster::GeoRaster(const GeoRaster& image, GeoFunction func)
		: GeoData(image), _GDALRasterBand(image._GDALRasterBand), _Masks(image._Masks), _NoData(image._NoData), _ValidStats(image._ValidStats), _Stats(image._Stats), //_ValidSize(image._ValidSize),
            _UnitsOut(image._UnitsOut), _minDC(image._minDC), _maxDC(image._maxDC), _K1(image._K1), _K2(image._K2), _Esun(image._Esun),
            _Atmosphere(image._Atmosphere), _Functions(image._Functions) {
        if (func.Function() != "") AddFunction(func);
		//std::cout << Basename() << ": GeoRaster copy (" << this << ")" << std::endl;
	}

	// Assignment
	GeoRaster& GeoRaster::operator=(const GeoRaster& image) {
		// Check for self assignment
		if (this == &image) return *this;
		//_GeoData = image._GeoData;
		GeoData::operator=(image);
		_GDALRasterBand = image._GDALRasterBand;
		_Masks = image._Masks;
		_NoData = image._NoData;
		_ValidStats = image._ValidStats;
		_Stats = image._Stats;
		_UnitsOut = image._UnitsOut;
		//_ValidSize = image._ValidSize;
		_minDC = image._minDC;
		_maxDC = image._maxDC;
		_K1 = image._K1;
		_K2 = image._K2;
		_Esun = image._Esun;
		_Functions = image._Functions;
		_Atmosphere = image._Atmosphere;
		//cout << _GeoImage->Basename() << ": " << ref << " references (GeoRaster Assignment)" << endl;
		return *this;
	}

    //! Process passed raster band into this raster band
    GeoRaster& GeoRaster::Process(const GeoRaster& img) {
        switch (DataType()) {
            case GDT_Byte: return GeoRasterIO<unsigned char>(*this).Process(img);
            case GDT_UInt16: return GeoRasterIO<unsigned short>(*this).Process(img);
            case GDT_Int16: return GeoRasterIO<short>(*this).Process(img);
            case GDT_UInt32: return GeoRasterIO<unsigned int>(*this).Process(img);
            case GDT_Int32: return GeoRasterIO<int>(*this).Process(img);
            case GDT_Float32: return GeoRasterIO<float>(*this).Process(img);
            case GDT_Float64: return GeoRasterIO<double>(*this).Process(img);
            default: return GeoRasterIO<unsigned char>(*this).Process(img);
            // TODO - remove default. This should throw exception
        }
    }

	string GeoRaster::Info(bool showstats) const {
		std::stringstream info;
		//info << _GeoImage->Basename() << " - b" << _GDALRasterBand->GetBand() << ":" << endl;
		info << XSize() << " x " << YSize() << " " << DataType() << ": " << Description();
		//info << " (GeoData: " << _GDALDataset.use_count() << " " << _GDALDataset << ")";
		//info << " RasterBand &" << _GDALRasterBand << endl;
        info << "\t\tGain = " << Gain() << ", Offset = " << Offset(); //<< ", Units = " << Units();
        if (_NoData)
			info << ", NoData = " << NoDataValue() << endl;
        else info << endl;
        if (showstats) {
            cimg_library::CImg<float> stats = this->ComputeStats();
        	info << "\t\tMin = " << stats(0) << ", Max = " << stats(1) << ", Mean = " << stats(2) << " =/- " << stats(3) << endl;
        }
        if (!_Functions.empty()) info << "\t\tFunctions:" << endl;
        for (unsigned int i=0;i<_Functions.size();i++) {
        	info << "\t\t\t" << _Functions[i].Function() << " " << _Functions[i].Operand() << endl;
        }
        if (!_Masks.empty()) info << "\tMasks:" << endl;
        for (unsigned int i=0;i<_Masks.size();i++) info << "\t\t\t" << _Masks[i].Info() << endl;
		//_GeoImage->GetGDALDataset()->Reference(); int ref = _GeoImage->GetGDALDataset()->Dereference();
		//info << "  GDALDataset: " << _GDALDataset.use_count() << " (&" << _GDALDataset << ")" << endl;
        return info.str();
	}

    //! Compute stats
    cimg_library::CImg<float> GeoRaster::ComputeStats() const {
        using cimg_library::CImg;

        if (_ValidStats) return _Stats;

        GeoRasterIO<double> img(*this);
        CImg<double> cimg;
        double count(0), total(0), val;
        double min(MaxValue()), max(MinValue());

        for (unsigned int iChunk=1; iChunk<=NumChunks(); iChunk++) {
            cimg = img.Read(iChunk);
            cimg_for(cimg,ptr,double) {
                if (*ptr != NoDataValue()) {
                    total += *ptr;
                    count++;
                    if (*ptr > max) max = *ptr;
                    if (*ptr < min) min = *ptr;
                }
            }
        }
        float mean = total/count;
        total = 0;
        double total3(0);
        for (unsigned int iChunk=1; iChunk<=NumChunks(); iChunk++) {
            cimg = img.Read(iChunk);
            cimg_for(cimg,ptr,double) {
                if (*ptr != NoDataValue()) {
                    val = *ptr-mean;
                    total += (val*val);
                    total3 += (val*val*val);
                }
            }
        }
        float var = total/count;
        float stdev = sqrt(var);
        float skew = (total3/count)/sqrt(var*var*var);
        _Stats = CImg<float>(6,1,1,1,(float)min,(float)max,mean,stdev,skew,count);
        _ValidStats = true;

        return _Stats;
    }

    float GeoRaster::Percentile(float p) const {
        CImg<float> stats = ComputeStats();
        unsigned int bins(100);
        CImg<float> hist = Histogram(bins,true) * 100;
        CImg<float> xaxis(bins);
        float interval( (stats(1)-stats(0))/((float)bins-1) );
        for (unsigned int i=0;i<bins;i++) xaxis[i] = stats(0) + i * interval;
        if (p == 0) return stats(0);
        if (p == 99) return stats(1);
        int ind(1);
        while(hist[ind] < p) ind++;
        float xind( (p-hist[ind-1])/(hist[ind]-hist[ind-1]) );
        return xaxis.linear_atX(ind-1+xind);
    }

    //! Compute histogram
    cimg_library::CImg<float> GeoRaster::Histogram(int bins, bool cumulative) const {
        CImg<double> cimg;
        CImg<float> stats = ComputeStats();
        CImg<float> hist(bins,1,1,1,0);
        long numpixels(0);
        float nodata = NoDataValue();
        GeoRasterIO<double> img(*this);
        for (unsigned int iChunk=1; iChunk<=NumChunks(); iChunk++) {
            cimg = img.Read(iChunk);
            cimg_for(cimg,ptr,double) {
                if (*ptr != nodata) {
                    hist[(unsigned int)( (*ptr-stats(0))*bins / (stats(1)-stats(0)) )]++;
                    numpixels++;
                }
            }
        }
        hist/=numpixels;
        if (cumulative) for (int i=1;i<bins;i++) hist[i] += hist[i-1];
        //if (Options::Verbose() > 3) hist.display_graph(0,3,1,"Pixel Value",stats(0),stats(1));
        return hist;
    }

} // namespace gip
