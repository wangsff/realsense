#!/usr/bin/env python 

'''
from 
https://github.com/IntelRealSense/librealsense/blob/jupyter/notebooks/distance_to_object.ipynb
'''
try:
    import cv2                                # state of the art computer vision algorithms library
except:
    print("no cv2 available")

import numpy as np                        # fundamental package for scientific computing
import matplotlib
import matplotlib.pyplot as plt           # 2D plotting library producing publication quality figures
from mpl_toolkits.axes_grid1 import make_axes_locatable
import pyrealsense2 as rs                 # Intel RealSense cross-platform open-source API
import json

try:
    import pyglet
    import pyglet.gl as gl
except:
    print("no pyglet or pyglet.gl available")


class lidar_control():
    '''
    librealsense2 wrappers for camera 
    control functions

    Author: P. Lewis
    Email:  p.lewis@ucl.ac.uk

    '''
 
    def __init__(self,decimate_scale=0,postprocessing=None,\
                      color=None,colour=None,\
                      nir=None,\
                      verbose=True):
        '''
        setup
        '''
        self.decimate_scale = 0 or decimate_scale
        self.postprocessing = False or postprocessing
        self.color = (colour or color) or False
        self.nir = nir or False
        self.camera = []
        self.settings = {}
        self.verbose = verbose
        self.dev = None

    def init(self,stop=True,self_test=True):
        '''
        find attached devices as start pipelines

        context derived from
        https://github.com/IntelRealSense/librealsense/tree/master/examples/multicam

        '''

        self.context = rs.context()
        self.config = rs.config()

        #
        # possible multiple devices
        # we store this as text in self.dev_info
        #
        self.active_devices = self.start_all_devices()
        self.sensors = self.context.query_all_sensors()
        print(self.sensors)
       
        if stop:
            self.stop_all_devices(self.active_devices)
            return 1
        else:
            return self.pipeline_profile

    def start_all_devices(self,reload=True,verbose=False):
        '''
        start all attached devices

        reload:
            - search again for all attached devices

        '''
        self.dev = (not reload and self.dev) or self.context.query_devices()
        verbose = verbose or self.verbose

        pipelines = []
        dev_infos = []
        pipeline_profiles = []
        for d in self.dev:
            pipe = rs.pipeline(self.context)
            dev_info = self.get_sensor_info(d)
            self.config.enable_device(dev_info['serial_number'])
            pipeline_profile = self.start(pipeline=pipe,config=self.config)
            if (self.verbose):
                print(f'started {dev_info["name"]} S/N: {dev_info["serial_number"]}')
            # store in list
            pipelines.append(pipe)
            dev_infos.append(dev_info)
            pipeline_profiles.append(pipeline_profile)
        self.active_devices = {'dev': self.dev,\
                'pipelines':pipelines,\
                'dev_infos':dev_infos,\
                'pipeline_profiles':pipeline_profiles}
        return self.active_devices
       
 
    def stop_all_devices(self,active_devices=None,verbose=False):
        active_devices = active_devices or self.active_devices
        verbose = self.verbose or verbose

        for pipe,dev_info in zip(active_devices['pipelines'],active_devices['dev_infos']):
            self.stop(pipeline=pipe)
            if verbose:
                print(f'stopped {dev_info["name"]} S/N: {dev_info["serial_number"]}')               

    def get_sensor_info(self,dev):
        camera_info = {}
        for k in rs.camera_info.__members__.keys():
            try:
                camera_info[k] = dev.get_info(rs.camera_info.__members__[k])
            except:
                pass
        return(camera_info)
        
    def start(self,pipeline=None,config=None):
        pipeline = pipeline or self.pipeline
        config = config or self.config
        try:
            self.pipeline_profile = pipeline.start(config)
            return self.pipeline_profile
        except:
            return None

    def stop(self,pipeline=None):
        pipeline = pipeline or self.pipeline
        try:
            pipeline.stop()
        except:
            print("failed attempt to stop")
        self.pipeline_profile = None
        return self.pipeline_profile

    def convert_fmt(self,fmt):
        '''
        from pyglet_pointcloud_viewer.py
        Processing blocks
        
        rs.format to pyglet format string
        ''' 
        return {
          rs.format.rgb8: 'RGB',
          rs.format.bgr8: 'BGR',
          rs.format.rgba8: 'RGBA',
          rs.format.bgra8: 'BGRA',
          rs.format.y8: 'L',
        }[fmt]


    def purge_camera(self):
        del self.camnera
        self.camera = []

    def load_settings(self,filename,append=False):
        '''
        load settings from json file

        These can be written from the realsense viewer

        Use append=True to append to any existing settings
        '''
        try:
            settings = json.load(open(filename,'r'))
            if append:
                self.settings.update(settings)
            else:
                self.settings = settings
        except:
            print(f'failed to load settings file {filename}')


    def get_pointcloud(self,depth_frame,image_frame,pc_file=None):
        '''
        get pointcloud data from depth and image frames

        option to save to ply file if pc_file is set

        '''
        pc = rs.pointcloud()
        pc.map_to(image_frame)
        points = pc.calculate(depth_frame)

        camera = {}
        camera['pc'] = pc
        camera['points'] = points
        if pc_file:
            camera['pc_file'] = pc_file
            print(f'writing point cloud to {pc_file}')
            points.export_to_ply(pc_file,image_frame)

        return camera

    def read_from_camera(self,size=(1024,768),\
                              fps=30,sample_rate=200):
        #start the frames pipe

        p = self.pipeline
        conf = self.config

        camera = {}

        # enable individual streams
        conf.enable_stream(rs.stream.depth, size[0],size[1], rs.format.z16, fps)
        camera['nir_stream'], camera['nir_format'] = rs.stream.infrared, rs.format.y8
        camera['image_stream'], camera['image_format'] = rs.stream.color, rs.format.rgb8
        conf.enable_stream(camera['image_stream'], size[0], size[1], camera['image_format'], sample_rate)
        conf.enable_stream(camera['nir_stream'], size[1], size[1], camera['nir_format'], sample_rate)
        conf.enable_stream(rs.stream.accel,rs.format.motion_xyz32f,200)
        conf.enable_stream(rs.stream.gyro,rs.format.motion_xyz32f,200)

        profile = p.get_active_profile()
        camera['depth_sensor'] = profile.get_device().first_depth_sensor()
        camera['depth_scale'] = camera['depth_sensor'].get_depth_scale()
        camera['depth_profile'] = rs.video_stream_profile(profile.get_stream(rs.stream.depth))
        camera['depth_intrinsics'] = camera['depth_profile'].get_intrinsics()
        camera['w'], camera['h'] = camera['depth_intrinsics'].width, camera['depth_intrinsics'].height
        # 
        # 

        if self.decimate_scale > 0:
            decimate = rs.decimation_filter()
            decimate.set_option(rs.option.filter_magnitude, int(2 ** decimate_level))
        
        colorizer = rs.colorizer()
    
        if self.postprocessing:
            camera['filters'] = [rs.disparity_transform(),
               rs.spatial_filter(),
               rs.temporal_filter(),
               rs.disparity_transform(False)]

        '''
        grab the frames
        '''
        camera['frames'] = p.wait_for_frames()

        if not camera['frames']:
            print('No frames from camera')
            return 0

        camera['depth'] = camera['frames'].get_depth_frame().as_video_frame()
        camera['color'] = camera['frames'].first(camera['image_stream']).as_video_frame()
        camera['nir'] = camera['frames'].first(camera['nir_stream']).as_video_frame()
 
        if self.decimate_scale > 0:
            camera['depth'] = decimate.process(camera['depth'])

        if self.postprocessing:
            for f in camera['filters']:
                camera['depth'] = f.process(camera['depth'])

        # Grab new intrinsics (may be changed by decimation)
        camera['depth_intrinsics'] = rs.video_stream_profile(camera['depth'].profile).get_intrinsics()
        camera['w'], camera['h'] = camera['depth_intrinsics'].width, camera['depth_intrinsics'].height

        camera['colorized_depth'] = colorizer.colorize(camera['depth'])

        self.stop()
        self.camera.append(camera)
        print('Done')
        return camera

    def to_np(self,frames):
        '''
        convert camera rs data to numpy arrays

        assume 
        '''
        results = [np.asanyarray(f.get_data()) for f in frames]
        return results
    
    # copy our data to pre-allocated buffers, this is faster than assigning...
    # pyglet will take care of uploading to GPU
    def copy(self,dst, src):
        """copy numpy array to pyglet array"""
        # timeit was mostly inconclusive, favoring slice assignment for safety
        np.array(dst, copy=False)[:] = src.ravel()
        # ctypes.memmove(dst, src.ctypes.data, src.nbytes)

    def not_here(self):
   
        vertex_list = pyglet.graphics.vertex_list(
        self.w * self.h, 'v3f/stream', 't2f/stream', 'n3f/stream')
 
        pc = rs.pointcloud()
        points = pc.calculate(depth_frame)
        pc.map_to(mapped_frame)

        # handle color source or size change
        fmt = convert_fmt(mapped_frame.profile.format())
        other_profile = rs.video_stream_profile(profile.get_stream(other_stream))


        global image_data
        if (image_data.format, image_data.pitch) != (fmt, color_source.strides[0]):
            empty = (gl.GLubyte * (self.w * self.h * 3))()
            image_data = pyglet.image.ImageData(self.w, self.h, fmt, empty)
            # copy image data to pyglet
            image_data.set_data(fmt, color_source.strides[0], color_source.ctypes.data)

        verts = np.asarray(points.get_vertices(2)).reshape(h, w, 3)
        texcoords = np.asarray(points.get_texture_coordinates(2))

        if len(vertex_list.vertices) != verts.size:
            vertex_list.resize(verts.size // 3)
            # need to reassign after resizing
            vertex_list.vertices = verts.ravel()
            vertex_list.tex_coords = texcoords.ravel()

   
        self.copy(vertex_list.vertices, verts)
        self.copy(vertex_list.tex_coords, texcoords)

        if self.lighting:
            # compute normals
            dy, dx = np.gradient(verts, axis=(0, 1))
            n = np.cross(dx, dy)

            # can use this, np.linalg.norm or similar to normalize, but OpenGL can do this for us, see GL_NORMALIZE above
            # norm = np.sqrt((n*n).sum(axis=2, keepdims=True))
            # np.divide(n, norm, out=n, where=norm != 0)

            # import cv2
            # n = cv2.bilateralFilter(n, 5, 1, 1)

            self.copy(vertex_list.normals, n)

        if keys[pyglet.window.key.E]:
            points.export_to_ply('./out.ply', mapped_frame)

    def plot(self,frames,centiles=None,\
                         titles=None,\
                         cmaps=None,\
                         figsize=None,\
                         file=None,\
                         dummy=False,\
                         transpose=False):


        result = self.to_np(frames)

        if dummy:
            matplotlib.use('Agg')
        figsize = figsize or (20,20)
        nr = (2 * ((len (result) +1)// 2))
        print(nr)
        nx = nr-nr//2
        shape = (nx,nr//nx)
        if transpose:
            shape = tuple(np.array(shape).T)

        fig, axs = plt.subplots(shape[1],shape[0],figsize=figsize)
        axs = np.array(axs).flatten()

        cmaps = cmaps or [None,plt.get_cmap('gray'),None,None]
        titles = titles or ['range','NIR','colour','colourised depth']
        print (shape)
        centiles = centiles or [(10,70),(25,95),(25,75),(5,95)]
      
        for i in range(nr):
            try:
                r = np.array(result[i].copy())
                '''r[r==0] = np.nan'''
                r_reste = r[r>0]
                rmin = np.percentile(r_reste,centiles[i][0])
                rmax = np.percentile(r,centiles[i][1])

                im = axs[i].imshow(r,vmin=rmin,vmax=rmax,cmap=cmaps[i])
                axs[i].title.set_text(titles[i])
                if i != 2:
                   divider = make_axes_locatable(axs[i])
                   cax = divider.append_axes('right', size='5%', pad=0.05)
                   fig.colorbar(im, cax=cax, orientation='vertical')
            except:
                pass
    
        if file:
            fig.savefig(file)

def main():
    l = lidar_control()
    l.load_settings('short_range_settings.json')

    l.init(stop=False)
    camera = l.read_from_camera()
    
    camera['pc'] = l.get_pointcloud(camera['depth'],\
                          camera['color'],\
                          pc_file='points.ply')

    frames = [camera['depth'],camera['nir'],camera['color'],camera['colorized_depth']]
    l.plot(frames,dummy=True,file='result.png')


if __name__== "__main__" :
    main()